#!/usr/bin/env python
import rospy
import behavior_tree as bt
import bt_ros
import numpy as np
from std_msgs.msg import String


class TestBT(object):
    def __init__(self):
        rospy.init_node("test_bt_node")
        self.move_publisher = rospy.Publisher("/navigation/move_command", String, queue_size=100)
        self.move_client = bt_ros.ActionClient(self.move_publisher)
        rospy.Subscriber("/response", String, self.move_client.response_callback)

        rospy.sleep(1)
        self.bt = bt.Root(
            bt_ros.MoveWaypoints([
                np.array([1, 1, 1]),
                np.array([2, 1, 1]),
                np.array([2, 2, 1]),
            ], "move_client"), action_clients={"move_client": self.move_client})
        self.bt_timer = rospy.Timer(rospy.Duration(0.1), self.timer_callback)

    def timer_callback(self, event):
        status = self.bt.tick()
        if status != bt.Status.RUNNING:
            self.bt_timer.shutdown()
        print("============== BT LOG ================")
        self.bt.log(0)


if __name__ == '__main__':
    try:
        node = TestBT()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass