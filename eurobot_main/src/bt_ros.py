import rospy
import threading
import behavior_tree as bt
from bt_parameters import BTVariable


class ActionClient(object):
    cmd_id = 0

    def __init__(self, cmd_publisher):
        self.cmd_publisher = cmd_publisher
        self.cmd_statuses = {}
        self.mutex = threading.Lock()

    def response_callback(self, data):
        self.mutex.acquire()
        data_splitted = data.data.split()
        cmd_id = data_splitted[0]
        status = data_splitted[1]
        if cmd_id in self.cmd_statuses.keys():
            self.cmd_statuses[cmd_id] = status
        self.mutex.release()

    def set_cmd(self, cmd, cmd_id=None):
        self.mutex.acquire()
        if cmd_id is None:
            cmd_id = str(self.cmd_id)
        self.cmd_id += 1
        self.cmd_statuses[cmd_id] = "running"
        self.cmd_publisher.publish(cmd_id + " " + cmd)
        self.mutex.release()
        return cmd_id

    def get_status(self, cmd_id):
        with self.mutex:
            status = self.cmd_statuses[cmd_id]
        return status


class ActionClientNode(bt.SequenceNode):
    def __init__(self, cmd, action_client_id, **kwargs):
        self.action_client_id = action_client_id
        self.cmd = BTVariable(cmd)
        self.cmd_id = BTVariable()

        self.start_move_node = bt.Latch(bt.ActionNode(self.start_action))
        bt.SequenceNode.__init__(self, [self.start_move_node, bt.ConditionNode(self.action_status)], **kwargs)

    def start_action(self):
        print("Start BT Action: " + self.cmd.get())
        self.cmd_id.set(self.root.action_clients[self.action_client_id].set_cmd(self.cmd.get()))

    def action_status(self):
        status = self.root.action_clients[self.action_client_id].get_status(self.cmd_id.get())
        if status == "running":
            return bt.Status.RUNNING
        elif status == "success":
            return bt.Status.SUCCESS
        else:
            return bt.Status.FAILED

    def reset(self):
        self.start_move_node.reset()

    def log(self, level):
        bt.BTNode.log(self, level)


class MoveWaypoints(bt.FallbackNode):
    def __init__(self, waypoints, action_client_id):
        self.waypoints = BTVariable(waypoints)

        self.move_to_waypoint_node = ActionClientNode("move 0 0 0", action_client_id, name="move_to_waypoint")

        bt.FallbackNode.__init__(self, [
            bt.ConditionNode(self.is_waypoints_empty),
            bt.SequenceNode([
                bt.ActionNode(self.choose_new_waypoint),
                self.move_to_waypoint_node,
                bt.ActionNode(self.remove_waypoint)
            ])
        ])

    def is_waypoints_empty(self):
        if len(self.waypoints.get()) > 0:
            return bt.Status.FAILED
        else:
            return bt.Status.SUCCESS

    def choose_new_waypoint(self):
        current_waypoint = self.waypoints.get()[0]
        self.move_to_waypoint_node.cmd.set("move_line %f %f %f" % tuple(current_waypoint))

    def remove_waypoint(self):
        self.waypoints.set(self.waypoints.get().pop(0))