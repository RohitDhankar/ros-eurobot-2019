#!/usr/bin/env python

import rospy
import behavior_tree as bt
import bt_ros
from std_msgs.msg import String
from bt_controller import SideStatus, BTController
from score_controller import ScoreController
from core_functions import *


class Tactics(object):
    def __init__(self):
        self.tfBuffer = tf2_ros.Buffer()
        self.tfListener = tf2_ros.TransformListener(self.tfBuffer)
        self.robot_coordinates = None


class YellowTactics(Tactics):
    def __init__(self):
        super(YellowTactics, self).__init__()

        self.approach_dist = rospy.get_param("approach_dist")  # 0.127 meters, distance from robot to puck where robot will try to grab it
        self.approach_dist = np.array(self.approach_dist)
        self.approach_vec = np.array([-1*self.approach_dist, 0, 0])  # 0.11

        # can be reached using rospy.get_param("purple_zone/red_cell_puck"
        self.red_cell_puck = rospy.get_param("yellow_zone/red_cell_puck")
        self.green_cell_puck = rospy.get_param("yellow_zone/green_cell_puck")
        self.blue_cell_puck = rospy.get_param("yellow_zone/blue_cell_puck")

        # use find origin
        self.first_puck_landing = np.array([self.red_cell_puck[0]+self.approach_dist,
                                           self.red_cell_puck[1],
                                           3.14])

        self.second_puck_landing = np.array([self.green_cell_puck[0],
                                            self.green_cell_puck[1]-self.approach_dist,
                                            1.57])

        self.third_puck_landing = np.array([self.blue_cell_puck[0],
                                           self.blue_cell_puck[1]-self.approach_dist,
                                           1.57])

        self.start_zone = rospy.get_param("yellow_zone/start_zone")

        self.blunium_collect_PREpos = rospy.get_param("yellow_zone/blunium_collect_PREpos")
        self.blunium_collect_pos = rospy.get_param("yellow_zone/blunium_collect_pos")

        self.accelerator_PREunloading_pos = rospy.get_param("yellow_zone/accelerator_PREunloading_pos")
        self.accelerator_unloading_pos = rospy.get_param("yellow_zone/accelerator_unloading_pos")
        self.accelerator_unloading_pos_far = rospy.get_param("yellow_zone/accelerator_unloading_pos_far")

        self.goldenium_PREgrab_pos = rospy.get_param("yellow_zone/goldenium_PREgrab_pos")
        self.goldenium_grab_pos = rospy.get_param("yellow_zone/goldenium_grab_pos")

        self.scales_goldenium_PREpos = rospy.get_param("yellow_zone/scales_goldenium_PREpos")
        self.scales_goldenium_pos = rospy.get_param("yellow_zone/scales_goldenium_pos")


class PurpleTactics(Tactics):
    def __init__(self):
        super(PurpleTactics, self).__init__()

        self.approach_dist = rospy.get_param("approach_dist")  # 0.127 meters, distance from robot to puck where robot will try to grab it
        self.approach_dist = np.array(self.approach_dist)
        self.approach_vec = np.array([-1*self.approach_dist, 0, 0])  # 0.11

        self.red_cell_puck = rospy.get_param("purple_zone/red_cell_puck")
        self.green_cell_puck = rospy.get_param("purple_zone/green_cell_puck")
        self.blue_cell_puck = rospy.get_param("purple_zone/blue_cell_puck")

        # use find origin
        self.first_puck_landing = np.array([self.red_cell_puck[0]-self.approach_dist,
                                           self.red_cell_puck[1],
                                           0])

        self.second_puck_landing = np.array([self.green_cell_puck[0],
                                            self.green_cell_puck[1]-self.approach_dist,
                                            1.57])

        self.third_puck_landing = np.array([self.blue_cell_puck[0],
                                           self.blue_cell_puck[1]-self.approach_dist,
                                           1.57])

        self.start_zone = rospy.get_param("purple_zone/start_zone")

        self.blunium_collect_PREpos = rospy.get_param("purple_zone/blunium_collect_PREpos")
        self.blunium_collect_pos = rospy.get_param("purple_zone/blunium_collect_pos")

        self.accelerator_PREunloading_pos = rospy.get_param("purple_zone/accelerator_PREunloading_pos")
        self.accelerator_unloading_pos = rospy.get_param("purple_zone/accelerator_unloading_pos")
        self.accelerator_unloading_pos_far = rospy.get_param("purple_zone/accelerator_unloading_pos_far")

        self.goldenium_PREgrab_pos = rospy.get_param("purple_zone/goldenium_PREgrab_pos")
        self.goldenium_grab_pos = rospy.get_param("purple_zone/goldenium_grab_pos")

        self.scales_goldenium_PREpos = rospy.get_param("purple_zone/scales_goldenium_PREpos")
        self.scales_goldenium_pos = rospy.get_param("purple_zone/scales_goldenium_pos")


class MainRobotBT(object):
    # noinspection PyTypeChecker
    def __init__(self, side_status=SideStatus.PURPLE):
        self.robot_name = rospy.get_param("robot_name")

        # publishers
        self.move_publisher = rospy.Publisher("navigation/command", String, queue_size=100)
        self.manipulator_publisher = rospy.Publisher("manipulator/command", String, queue_size=100)

        # clients
        self.move_client = bt_ros.ActionClient(self.move_publisher)
        self.manipulator_client = bt_ros.ActionClient(self.manipulator_publisher)

        # usefull child node
        # self.move_to_waypoint_node = bt_ros.ActionClientNode("move 0 0 0", action_client_id, name="move_to_waypoint")

        # choose side
        self.purple_tactics = PurpleTactics()
        self.yellow_tactics = YellowTactics()

        self.side_status = side_status

        if self.side_status == SideStatus.PURPLE:
            self.tactics = self.purple_tactics
        elif self.side_status == SideStatus.YELLOW:
            self.tactics = self.yellow_tactics
        else:
            self.tactics = None

        self.current_strategy = None

        self.bt = None
        self.bt_timer = None

        # TODO: pucks in front of starting cells are random, so while we aren't using camera
        #       will call them REDIUM  (it doesn't matter, because in this strategy we move them all to acc)

        # TODO: It will matter in case big robot faces hard collision and need to unload pucks in starting cells

        # score master
        # self.is_puck_grabbed = grab_status  TODO

        # self.collected_pucks = bt.BTVariable([])
        # self.SC = ScoreController(self.collected_pucks)

        self.is_puck_first_flag = True

        # subscribers
        rospy.Subscriber("navigation/response", String, self.move_client.response_callback)
        rospy.Subscriber("manipulator/response", String, self.manipulator_client.response_callback)

    def is_robot_empty(self):
        if len(self.collected_pucks.get()) > 0:
            return bt.Status.FAILED
        else:
            return bt.Status.SUCCESS

    def is_puck_first(self):
        if self.is_puck_first_flag:
            self.is_puck_first_flag = False
            return bt.Status.SUCCESS
        else:
            return bt.Status.FAILED

    # def strategy_vovan(self):
 

    #    return strategy

    def start(self):

        # red_cell_puck = bt.SequenceWithMemoryNode([
        #     bt_ros.MoveLineToPoint(self.tactics.first_puck_landing, "move_client"),
        #     bt_ros.StartCollectGround("manipulator_client"),
        #     # self.SC.score_master("add", "REDIUM")  # FIXME: color is undetermined without camera!
        # ])

        # green_cell_puck = bt.SequenceWithMemoryNode([
        #     bt.ParallelWithMemoryNode([
        #         bt_ros.CompleteCollectGround("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.second_puck_landing, "move_client"),
        #     ], threshold=2),
        #     bt_ros.StartCollectGround("manipulator_client"),
        #     # self.SC.score_master("add", "REDIUM")  # FIXME: color is undetermined without camera!
        # ]),

        # blue_cell_puck = bt.SequenceWithMemoryNode([
        #     bt.ParallelWithMemoryNode([
        #         bt_ros.CompleteCollectGround("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.third_puck_landing, "move_client"),
        #     ], threshold=2),
        #     bt_ros.StartCollectGround("manipulator_client"),
        #     # self.SC.score_master("add", "REDIUM")  # FIXME: color is undetermined without camera!
        # ]),

        # blunium_acc = bt.SequenceWithMemoryNode([
        #     bt.ParallelWithMemoryNode([
        #         bt_ros.CompleteCollectGround("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.blunium_collect_PREpos, "move_client"),
        #     ], threshold=2),
        #     bt_ros.StartCollectBlunium("manipulator_client"),
        #     bt_ros.MoveLineToPoint(self.tactics.blunium_collect_pos, "move_client"),
        #     bt_ros.CompleteCollectGround("manipulator_client"),
        #     # self.SC.score_master("add", "BLUNIUM"),
        # ])

        # go_to_acc = bt.ParallelWithMemoryNode([
        #     bt_ros.SetManipulatortoUp("manipulator_client"),
        #     bt_ros.MoveLineToPoint(self.tactics.accelerator_PREunloading_pos, "move_client"),
        #     # FIXME Sasha will change unloading mechanism
        #     bt_ros.StepUp("manipulator_client"),
        # ], threshold=3)

        # # unload_acc = bt.FallbackNode([
        # #                 bt.ConditionNode(self.is_robot_empty),
        # #                 bt.SequenceNode([
        # #                     bt.SequenceWithMemoryNode([
        # #                         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
        # #                         bt_ros.UnloadAccelerator("manipulator_client"),
        # #                         # self.SC.score_master("unload", "ACC"),
        # #                         bt.FallbackNode([
        # #                             bt.SequenceNode([
        # #                                 bt.ConditionNode(self.is_puck_first_flag),
        # #                                 # self.SC.score_master("reward", "UNLOCK_GOLDENIUM_BONUS"),
        # #                             ]),
        # #                             bt.ConditionNode(lambda: bt.Status.SUCCESS)
        # #                         ]),
        # #                         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos_far, "move_client"),
        # #                     ]),
        # #                     bt.ConditionNode(lambda: bt.Status.RUNNING)
        # #                 ])
        # #             ])

        # # to make sure that the LAST puck is unloaded

        # temporary_move = bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client")

        # collect_goldenium = bt.SequenceWithMemoryNode([
        #     bt_ros.MoveLineToPoint(self.tactics.goldenium_PREgrab_pos, "move_client"),
        #     bt.ParallelWithMemoryNode([
        #         bt_ros.SetManipulatortoGoldenium("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.goldenium_grab_pos, "move_client"),
        #     ], threshold=2),
        #     bt_ros.GrabGoldeniumAndHoldUp("manipulator_client"),
        #     # self.SC.score_master("add", "GOLDENIUM"),
        #     # self.SC.score_master("reward", "GRAB_GOLDENIUM_BONUS"),
        # ])

        # unload_goldenium = bt.SequenceWithMemoryNode([
        #     bt_ros.MoveLineToPoint(self.tactics.scales_goldenium_PREpos, "move_client"),
        #     bt_ros.MoveLineToPoint(self.tactics.scales_goldenium_pos, "move_client"),
        #     bt_ros.UnloadGoldenium("manipulator_client"),
        #     # self.SC.score_master("unload", "SCALES")
        # ])

        # move_finish = bt.SequenceWithMemoryNode([
        #     bt_ros.MoveLineToPoint(self.tactics.first_puck_landing, "move_client"),
        #     bt_ros.MoveLineToPoint(self.tactics.start_zone, "move_client"),
        # ])

        # self.tree = bt.SequenceWithMemoryNode([
        #     default_state,
        #     red_cell_puck,
        #     green_cell_puck,
        #     blue_cell_puck,
        #     blunium_acc,
        #     go_to_acc,
        #     unload_acc,
        #     temporary_move,
        #     collect_goldenium,
        #     unload_goldenium,
        #     move_finish
        #     ])

        tree = bt.SequenceWithMemoryNode([
            bt_ros.MoveLineToPoint(self.tactics.first_puck_landing, "move_client"),
            bt_ros.StartCollectGround("manipulator_client"),
    
            # bt.FallbackWithMemoryNode([
            #     bt.SequenceWithMemoryNode([
            #         bt.ConditionNode(self.is_puck_grabbed),
            #         bt.ActionNode(lambda: self.score_master.add("   FIXME !!!!!!    ")),
            #         bt.ActionNode(self.is_puck_grabbed.reset)]),
            #     bt.ActionNode(self.is_puck_grabbed.reset)
            #     ]),
    
    
            bt.ParallelWithMemoryNode([
                bt_ros.CompleteCollectGround("manipulator_client"),
                bt_ros.MoveLineToPoint(self.tactics.second_puck_landing, "move_client"),
            ], threshold=2),
            bt_ros.StartCollectGround("manipulator_client"),
    
            bt.ParallelWithMemoryNode([
                bt_ros.CompleteCollectGround("manipulator_client"),
                bt_ros.MoveLineToPoint(self.tactics.third_puck_landing, "move_client"),
            ], threshold=2),
            bt_ros.StartCollectGround("manipulator_client"),
    
            bt.ParallelWithMemoryNode([
                bt_ros.CompleteCollectGround("manipulator_client"),
                bt_ros.MoveLineToPoint(self.tactics.blunium_collect_PREpos, "move_client"),
            ], threshold=2),
            bt_ros.StartCollectBlunium("manipulator_client"),
            bt_ros.MoveLineToPoint(self.tactics.blunium_collect_pos, "move_client"),
            bt_ros.CompleteCollectGround("manipulator_client"),
    
            bt_ros.SetManipulatortoUp("manipulator_client"),
            bt_ros.MoveLineToPoint(self.tactics.accelerator_PREunloading_pos, "move_client"),
            # FIXME Sasha have to fix height of unloading mechanism
            bt_ros.StepUp("manipulator_client"),
    
            # unload first in acc
            bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
            bt_ros.UnloadAccelerator("manipulator_client"),
            bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos_far, "move_client"),
    
            # unload second in acc
            bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
            bt_ros.UnloadAccelerator("manipulator_client"),
            bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos_far, "move_client"),
    
            # unload third in acc
            bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
            bt_ros.UnloadAccelerator("manipulator_client"),
            bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos_far, "move_client"),
    
            # unload forth in acc
            bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
            bt_ros.UnloadAccelerator("manipulator_client"),
            bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos_far, "move_client"),
    
            # to make sure that the LAST puck is unloaded
            bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
    
            # collect Goldenium
            bt_ros.MoveLineToPoint(self.tactics.goldenium_PREgrab_pos, "move_client"),
            bt_ros.SetManipulatortoGoldenium("manipulator_client"),
            bt_ros.MoveLineToPoint(self.tactics.goldenium_grab_pos, "move_client"),
            bt_ros.GrabGoldeniumAndHoldUp("manipulator_client"),
    
            # move to scales and unload
            bt_ros.MoveLineToPoint(self.tactics.scales_goldenium_PREpos, "move_client"), # FIXME
            bt_ros.MoveLineToPoint(self.tactics.scales_goldenium_pos, "move_client"), # FIXME
            bt_ros.UnloadGoldenium("manipulator_client"),
    
            bt_ros.MoveLineToPoint(self.tactics.first_puck_landing, "move_client"),
            bt_ros.MoveLineToPoint(self.tactics.start_zone, "move_client"),
        ])
        print("here ------------------------")
        print(tree)
        print(type(tree))
        print("here ------------------------")
        self.bt = bt.Root(tree,
                    action_clients={"move_client": self.move_client, "manipulator_client": self.manipulator_client})

        # self.bt = bt.Root(
        #     bt.SequenceWithMemoryNode([
        #         bt_ros.MoveLineToPoint(self.tactics.first_puck_landing, "move_client"),
        #         bt_ros.StartCollectGround("manipulator_client"),
        
        #         # bt.FallbackWithMemoryNode([
        #         #     bt.SequenceWithMemoryNode([
        #         #         bt.ConditionNode(self.is_puck_grabbed),
        #         #         bt.ActionNode(lambda: self.score_master.add("   FIXME !!!!!!    ")),
        #         #         bt.ActionNode(self.is_puck_grabbed.reset)]),
        #         #     bt.ActionNode(self.is_puck_grabbed.reset)
        #         #     ]),
        
        
        #         bt.ParallelWithMemoryNode([
        #             bt_ros.CompleteCollectGround("manipulator_client"),
        #             bt_ros.MoveLineToPoint(self.tactics.second_puck_landing, "move_client"),
        #         ], threshold=2),
        #         bt_ros.StartCollectGround("manipulator_client"),
        
        #         bt.ParallelWithMemoryNode([
        #             bt_ros.CompleteCollectGround("manipulator_client"),
        #             bt_ros.MoveLineToPoint(self.tactics.third_puck_landing, "move_client"),
        #         ], threshold=2),
        #         bt_ros.StartCollectGround("manipulator_client"),
        
        #         bt.ParallelWithMemoryNode([
        #             bt_ros.CompleteCollectGround("manipulator_client"),
        #             bt_ros.MoveLineToPoint(self.tactics.blunium_collect_PREpos, "move_client"),
        #         ], threshold=2),
        #         bt_ros.StartCollectBlunium("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.blunium_collect_pos, "move_client"),
        #         bt_ros.CompleteCollectGround("manipulator_client"),
        
        #         bt_ros.SetManipulatortoUp("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.accelerator_PREunloading_pos, "move_client"),
        #         # FIXME Sasha have to fix height of unloading mechanism
        #         bt_ros.StepUp("manipulator_client"),
        
        #         # unload first in acc
        #         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
        #         bt_ros.UnloadAccelerator("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos_far, "move_client"),
        
        #         # unload second in acc
        #         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
        #         bt_ros.UnloadAccelerator("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos_far, "move_client"),
        
        #         # unload third in acc
        #         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
        #         bt_ros.UnloadAccelerator("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos_far, "move_client"),
        
        #         # unload forth in acc
        #         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
        #         bt_ros.UnloadAccelerator("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos_far, "move_client"),
        
        #         # to make sure that the LAST puck is unloaded
        #         bt_ros.MoveLineToPoint(self.tactics.accelerator_unloading_pos, "move_client"),
        
        #         # collect Goldenium
        #         bt_ros.MoveLineToPoint(self.tactics.goldenium_PREgrab_pos, "move_client"),
        #         bt_ros.SetManipulatortoGoldenium("manipulator_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.goldenium_grab_pos, "move_client"),
        #         bt_ros.GrabGoldeniumAndHoldUp("manipulator_client"),
        
        #         # move to scales and unload
        #         bt_ros.MoveLineToPoint(self.tactics.scales_goldenium_PREpos, "move_client"), # FIXME
        #         bt_ros.MoveLineToPoint(self.tactics.scales_goldenium_pos, "move_client"), # FIXME
        #         bt_ros.UnloadGoldenium("manipulator_client"),
        
        #         bt_ros.MoveLineToPoint(self.tactics.first_puck_landing, "move_client"),
        #         bt_ros.MoveLineToPoint(self.tactics.start_zone, "move_client"),
        #     ]),
        #     action_clients={"move_client": self.move_client, "manipulator_client": self.manipulator_client})

        self.bt_timer = rospy.Timer(rospy.Duration(0.1), self.timer_callback)

    def change_side(self, side):
        if side == SideStatus.PURPLE:
            self.tactics = self.purple_tactics
        elif side == SideStatus.YELLOW:
            self.tactics = self.yellow_tactics
        else:
            self.tactics = None

    def timer_callback(self, event):

        status = self.bt.tick()
        if status != bt.Status.RUNNING:
            self.bt_timer.shutdown()
        print("============== BT LOG ================")
        self.bt.log(0)


if __name__ == '__main__':
    try:
        rospy.init_node("main_robot_BT")
        main_robot_bt = MainRobotBT()
        bt_controller = BTController(main_robot_bt)
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
