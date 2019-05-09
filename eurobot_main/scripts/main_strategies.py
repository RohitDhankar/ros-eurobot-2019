#!/usr/bin/env python

import rospy
import numpy as np
import behavior_tree as bt
import bt_ros
import tf2_ros
from tf.transformations import euler_from_quaternion
from core_functions import *
from std_msgs.msg import String
from tactics_math import *
from score_controller import ScoreController
from visualization_msgs.msg import MarkerArray
from collect_chaos import CollectChaos
from main_robot_bt import MainRobotBT
from bt_controller import SideStatus, BTController
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon


class Strategy(MainRobotBT):
    def __init__(self):
        super(Strategy, self).__init__()
        self.robot_name = rospy.get_param("robot_name")
        self.sign = 1
        self.param = rospy.get_param("start_side")

        self.vertical_pucks_approach_dist = rospy.get_param("vertical_pucks_approach_dist")
        self.horiz_pucks_approach_dist = np.array(rospy.get_param("horiz_pucks_approach_dist"))  # 0.127 meters, distance from robot to puck where robot will try to grab it
        self.approach_vec = np.array([-1 * self.horiz_pucks_approach_dist, 0, 0])
        self.drive_back_dist = np.array(rospy.get_param("drive_back_dist"))  # FIXME
        self.drive_back_vec = np.array([-1*self.drive_back_dist, 0, 0])

        self.gnd_spacing = rospy.get_param("ground_spacing_dist")
        self.robot_outer_radius = rospy.get_param("robot_outer_radius")
        self.stick_len = rospy.get_param("stick_len")

        self.delta = rospy.get_param("approach_delta")  # FIXME
        self.scale_factor = np.array(rospy.get_param("scale_factor"))  # used in calculating outer bissectrisa for hull's angles
        # self.critical_angle = np.pi * 2/3
        self.critical_angle = rospy.get_param("critical_angle")

        self.known_chaos_pucks = bt.BTVariable(np.array([]))  # (x, y, id, r, g, b)
        self.incoming_puck_color = bt.BTVariable(None)
        self.collected_pucks = bt.BTVariable(np.array([]))
        self.is_observed_flag = bt.BTVariable(False)
        self.is_secondary_responding = False
        self.secondary_coords = np.array([0, 0, 0])
        self.main_coords = None
        self.score_master = ScoreController(self.collected_pucks, self.robot_name)

        self.red_cell_puck = rospy.get_param(self.robot_name + "/" + self.param + "/red_cell_puck")
        self.blunium = rospy.get_param(self.robot_name + "/" + self.param + "/blunium")
        self.goldenium = rospy.get_param(self.robot_name + "/" + self.param + "/goldenium")
        self.scales_area = np.array(rospy.get_param(self.robot_name + "/" + self.param + "/scales_area"))
        self.chaos_center = rospy.get_param(self.robot_name + "/" + self.param + "/chaos_center")

        self.first_puck_landing = np.array([self.red_cell_puck[0] + self.sign * self.horiz_pucks_approach_dist - self.sign * self.delta,
                                            self.red_cell_puck[1],
                                            1.57 + self.sign * 1.57])  # 3.14 / 0

        self.first_puck_landing_finish = np.array([self.red_cell_puck[0],
                                                    self.red_cell_puck[1] - 0.04,
                                                    1.57])

        self.second_puck_landing = np.array([self.red_cell_puck[0],
                                             self.red_cell_puck[1] + self.gnd_spacing - self.horiz_pucks_approach_dist + self.delta,
                                             1.57])

        self.third_puck_landing = np.array([self.red_cell_puck[0],
                                            self.red_cell_puck[1] + 2 * self.gnd_spacing - self.horiz_pucks_approach_dist + self.delta,
                                            1.57])

        self.third_puck_rotate_pose = np.array([self.chaos_center[0],
                                                self.chaos_center[1] - 0.3,
                                                -1.57 - self.sign * 0.785])  # -2.35 / -0.78

        self.blunium_prepose = np.array([self.blunium[0] + self.sign * 0.07,
                                         self.blunium[1] + 0.35,
                                         -0.52])

        self.blunium_collect_PREpos = np.array([self.blunium[0],
                                                self.blunium[1] + 0.35,
                                                -1.57])

        self.blunium_collect_pos = np.array([self.blunium[0],
                                            self.blunium[1] + self.vertical_pucks_approach_dist,  # 0.185,  # FIXME move 0.185 in params
                                            self.blunium_collect_PREpos[2]])

        self.blunium_collect_pos_side = np.array([self.blunium[0] + self.sign * 0.03,
                                                    self.blunium_collect_pos[1],
                                                    self.blunium_collect_PREpos[2]])

        self.blunium_start_push_pose = np.array([self.blunium_prepose[0],
                                                 self.blunium[1] + self.robot_outer_radius,
                                                 self.blunium_prepose[2]])

        self.blunium_end_push_pose = np.array([self.blunium_start_push_pose[0] - self.sign * 0.08,
                                               self.blunium_start_push_pose[1],
                                               self.blunium_start_push_pose[2]])

        self.blunium_get_back_pose = np.array([self.blunium_end_push_pose[0],
                                               self.blunium_end_push_pose[1] + 0.1,
                                               self.blunium_end_push_pose[2]])

        self.accelerator_PREunloading_pos = np.array([self.blunium_end_push_pose[0] - self.sign * 0.22,
                                                       self.blunium[1] + 0.13,
                                                       0.56])

        self.goldenium_1_PREgrab_pos = np.array([self.goldenium[0],
                                               self.goldenium[1] + 0.35,
                                               self.accelerator_PREunloading_pos[2]])

        self.goldenium_2_PREgrab_pos = np.array([self.goldenium[0],
                                               self.goldenium[1] + 0.28,
                                               -1.57])

        self.goldenium_grab_pos = np.array([self.goldenium[0],
                                               self.goldenium[1] + self.vertical_pucks_approach_dist,  # 0.185
                                               self.goldenium_2_PREgrab_pos[2]])

        self.goldenium_back_pose = np.array([self.goldenium[0],
                                            self.goldenium_grab_pos[1] + 0.09,
                                            self.goldenium_2_PREgrab_pos[2]])

        self.goldenium_back_rot_pose = np.array([self.goldenium[0],
                                                 self.goldenium_back_pose[1],
                                                 1.57 - self.sign * 0.5])  # 1.07 / 2.07

        self.scales_goldenium_PREpos = np.array([self.chaos_center[0] - self.sign * 0.1,
                                                 self.chaos_center[1] - 0.6,
                                                 1.57 - self.sign * 0.17])  # 1.4 / 1.74

        self.scales_goldenium_pos = np.array([self.chaos_center[0] - self.sign * 0.3,
                                              self.chaos_center[1] + 0.37,
                                              1.57 + self.sign * 0.26])  # 1.83 / 1.31

        # TODO: pucks in front of starting cells are random, so while we aren't using camera
        #       will call them REDIUM  (it doesn't matter, because in this strategy we move them all to acc)
        #       It will matter in case big robot faces hard collision and need to unload pucks in starting cells

        self.pucks_subscriber = rospy.Subscriber("/pucks", MarkerArray, self.pucks_callback, queue_size=1)
        rospy.Subscriber("navigation/response", String, self.move_client.response_callback)
        rospy.Subscriber("manipulator/response", String, self.manipulator_client.response_callback)

    def pucks_callback(self, data):
        # [(0.95, 1.1, 3, 0, 0, 1), ...] - blue, id=3  IDs are not guaranteed to be the same from frame to frame
        # red (1, 0, 0)
        # green (0, 1, 0)
        # blue (0, 0, 1)
        rospy.loginfo(data)

        if len(self.known_chaos_pucks.get()) == 0:
            try:
                new_observation_pucks = [[marker.pose.position.x,
                                          marker.pose.position.y,
                                          marker.id,
                                          marker.color.r,
                                          marker.color.g,
                                          marker.color.b] for marker in data.markers]

                if len(new_observation_pucks) == 4:
                    new_observation_pucks = np.array(new_observation_pucks)

                    self.known_chaos_pucks.set(new_observation_pucks)
                    self.is_observed_flag.set(True)
                    rospy.loginfo("Got pucks observation:")
                    rospy.loginfo(self.known_chaos_pucks.get())
                    self.pucks_subscriber.unregister()

            except Exception:  # FIXME
                rospy.loginfo("list index out of range - no visible pucks on the field ")

    def is_observed(self):
        # rospy.loginfo("is observed?")
        if self.is_observed_flag.get():
            # rospy.loginfo('YES! Got all pucks coords')
            return bt.Status.SUCCESS
        else:
            rospy.loginfo('Still waiting for the cam, known: ' + str(len(self.known_chaos_pucks.get())))
            return bt.Status.FAILED

    def is_robot_empty(self):
        rospy.loginfo("pucks inside")
        rospy.loginfo(self.collected_pucks.get())
        if len(self.collected_pucks.get()) == 0:
            rospy.loginfo('All pucks unloaded')
            return bt.Status.SUCCESS
        else:
            rospy.loginfo('Pucks inside: ' + str(len(self.collected_pucks.get())))
            return bt.Status.FAILED

    def is_robot_empty_1(self):
        rospy.loginfo("pucks inside")
        rospy.loginfo(self.collected_pucks.get())
        if len(self.collected_pucks.get()) == 0:
            rospy.loginfo('All pucks unloaded')
            return bt.Status.SUCCESS
        else:
            rospy.loginfo('Pucks inside: ' + str(len(self.collected_pucks.get())))
            return bt.Status.RUNNING

    def is_scales_landing_free(self):
        """
        Secondary may be:
        - not working at all -- than
        - somewhere else and we know of it
        - working but we don't get info about it -- wait

        if we don't get secondary coords - wait 10 sec
        if we get them, wait until it gets out of zone

        """
        self.is_secondary_responding = self.update_secondary_coords()
        rospy.loginfo("Checking if scales are available to approach...")

        area = self.strategy.scales_area
        robot = self.secondary_coords  # can be 0, 0, 0  or  some value

        point = Point(robot[0], robot[1])
        polygon = Polygon([area[0], area[1], area[2], area[3]])

        if not self.is_secondary_responding:
            rospy.sleep(5)
            return bt.Status.SUCCESS
        else:
            print("got coords in condition:")
            print(self.secondary_coords)
            if polygon.contains(point):
                rospy.loginfo('Landing busy')
                return bt.Status.RUNNING
            else:
                rospy.loginfo('Landing is free to go')
                return bt.Status.SUCCESS

    def update_main_coords(self):
        try:
            trans_main = self.tfBuffer.lookup_transform('map', "main_robot", rospy.Time(0))  # 0 means last measurment
            q_main = [trans_main.transform.rotation.x,
                      trans_main.transform.rotation.y,
                      trans_main.transform.rotation.z,
                      trans_main.transform.rotation.w]
            angle_main = euler_from_quaternion(q_main)[2] % (2 * np.pi)
            self.main_coords = np.array([trans_main.transform.translation.x,
                                         trans_main.transform.translation.y,
                                         angle_main])
            rospy.loginfo("main coords: " + str(self.main_coords))
            # return True
        except (tf2_ros.LookupException, tf2_ros.ConnectivityException, tf2_ros.ExtrapolationException) as msg:
            rospy.logwarn(str(msg))
            # return False

    def update_secondary_coords(self):
        try:
            trans_secondary = self.tfBuffer.lookup_transform('map', "secondary_robot", rospy.Time(0))
            q_secondary = [trans_secondary.transform.rotation.x,
                           trans_secondary.transform.rotation.y,
                           trans_secondary.transform.rotation.z,
                           trans_secondary.transform.rotation.w]
            angle_secondary = euler_from_quaternion(q_secondary)[2] % (2 * np.pi)
            self.secondary_coords = np.array([trans_secondary.transform.translation.x,
                                              trans_secondary.transform.translation.y,
                                              angle_secondary])

            rospy.loginfo("=============================================================")
            rospy.loginfo("Got coords of secondary robot: ")
            rospy.loginfo(self.secondary_coords)
            return True

        except (tf2_ros.LookupException, tf2_ros.ConnectivityException, tf2_ros.ExtrapolationException) as msg:
            rospy.logwarn(str(msg))
            return False


class PushBluniumStrategy(Strategy):
    def __init__(self, side):
        super(PushBluniumStrategy, self).__init__()

        if side == SideStatus.PURPLE:
            self.param = "purple_side"
            self.side_sign = -1
        elif side == SideStatus.YELLOW:
            self.param = "yellow_side"
            self.side_sign = 1

        red_cell_puck = bt.SequenceWithMemoryNode([
                            bt_ros.MoveLineToPoint(self.tactics.first_puck_landing, "move_client"),
                            bt.FallbackWithMemoryNode([
                                bt.SequenceWithMemoryNode([
                                    bt_ros.BlindStartCollectGround("manipulator_client"),
                                    bt.ActionNode(lambda: self.score_master.add("REDIUM")),  # FIXME: color is undetermined without camera!
                                    bt.ParallelWithMemoryNode([
                                        bt_ros.CompleteCollectGround("manipulator_client"),
                                        bt_ros.MoveLineToPoint(self.tactics.first_puck_landing_finish, "move_client"),
                                    ], threshold=2),
                                ]),
                                bt.ParallelWithMemoryNode([
                                    bt_ros.SetManipulatortoWall("manipulator_client"),
                                    bt_ros.MoveLineToPoint(self.tactics.first_puck_landing_finish, "move_client"),
                                ], threshold=2),
                            ]),
                        ])

        green_cell_puck = bt.SequenceWithMemoryNode([
                            bt_ros.MoveLineToPoint(self.tactics.second_puck_landing, "move_client"),
                            bt.FallbackWithMemoryNode([
                                bt.SequenceWithMemoryNode([
                                    bt_ros.BlindStartCollectGround("manipulator_client"),
                                    bt.ActionNode(lambda: self.score_master.add("REDIUM")),  # FIXME: color is undetermined without camera!
                                    bt.ParallelWithMemoryNode([
                                        bt_ros.CompleteCollectGround("manipulator_client"),
                                        bt_ros.MoveLineToPoint(self.tactics.third_puck_landing, "move_client"),
                                    ], threshold=2),
                                ]),
                                bt.ParallelWithMemoryNode([
                                    bt_ros.SetManipulatortoWall("manipulator_client"),
                                    bt_ros.MoveLineToPoint(self.tactics.third_puck_landing, "move_client"),
                                ], threshold=2),
                            ])
                        ])

        blue_cell_puck = bt.SequenceWithMemoryNode([
                            bt.FallbackWithMemoryNode([
                                bt.SequenceWithMemoryNode([
                                    bt_ros.BlindStartCollectGround("manipulator_client"),
                                    bt.ActionNode(lambda: self.score_master.add("REDIUM")),  # FIXME: color is undetermined without camera!
                                    bt.ParallelWithMemoryNode([
                                        bt_ros.CompleteCollectGround("manipulator_client"),
                                        bt_ros.MoveLineToPoint(self.tactics.third_puck_rotate_pose, "move_client"),
                                    ], threshold=2),
                                ]),
                                bt.ParallelWithMemoryNode([
                                    bt_ros.SetManipulatortoUp("manipulator_client"),  # FIXME when adding chaos
                                    bt_ros.MoveLineToPoint(self.tactics.third_puck_rotate_pose, "move_client"),
                                ], threshold=2),
                            ])
                        ])

        finish_move_blunium_and_push = bt.SequenceWithMemoryNode([
                                            bt_ros.MoveLineToPoint(self.tactics.blunium_start_push_pose, "move_client"),
                                            bt.ParallelWithMemoryNode([
                                                bt_ros.MainSetManipulatortoGround("manipulator_client"),  # FIXME when adding chaos
                                                bt_ros.MoveLineToPoint(self.tactics.blunium_start_push_pose, "move_client"),
                                            ], threshold=2),
                                            # bt_ros.MoveLineToPoint(self.tactics.blunium_prepose, "move_client"),
                                            bt_ros.MoveLineToPoint(self.tactics.blunium_end_push_pose, "move_client"),
                                            bt.ActionNode(lambda: self.score_master.add("BLUNIUM")),
                                            bt.ActionNode(lambda: self.score_master.unload("ACC")),
                                            bt.ActionNode(lambda: self.score_master.reward("UNLOCK_GOLDENIUM_BONUS")),
                                        ])

        approach_acc = bt.SequenceWithMemoryNode([
                            bt_ros.MoveLineToPoint(self.tactics.blunium_get_back_pose, "move_client"),
                            bt_ros.MoveLineToPoint(self.tactics.accelerator_PREunloading_pos, "move_client"),  # FIXME try Arc
                            bt_ros.SetSpeedSTM([0, -0.1, 0], 0.6, "stm_client"),
                        ])

        push_unload_first_in_acc = bt.SequenceWithMemoryNode([
                                    bt_ros.StepperUp("manipulator_client"),  # FIXME do we need to do that? NO if all 7 pucks inside
                                    bt_ros.UnloadAccelerator("manipulator_client"),
                                    bt.ActionNode(lambda: self.score_master.unload("ACC")),
                                ])

        unload_acc = bt.SequenceNode([
                        bt.FallbackNode([
                            bt.ConditionNode(self.is_robot_empty),
                            bt.SequenceWithMemoryNode([
                                bt_ros.UnloadAccelerator("manipulator_client"),
                                bt.ActionNode(lambda: self.score_master.unload("ACC")),
                            ])
                        ]),
                        bt.ConditionNode(self.is_robot_empty_1)
                    ])

        collect_goldenium = bt.SequenceWithMemoryNode([
                                bt_ros.MoveLineToPoint(self.tactics.goldenium_1_PREgrab_pos, "move_client"),
                                bt_ros.MoveLineToPoint(self.tactics.goldenium_2_PREgrab_pos, "move_client"),
                                bt_ros.StartCollectGoldenium("manipulator_client"),
                                bt_ros.MoveLineToPoint(self.tactics.goldenium_grab_pos, "move_client"),
                                bt_ros.GrabGoldeniumAndHoldUp("manipulator_client"),
                                bt.ActionNode(lambda: self.score_master.add("GOLDENIUM")),
                                bt.ActionNode(lambda: self.score_master.reward("GRAB_GOLDENIUM_BONUS")),
                            ])

        # collect_goldenium = bt.SequenceWithMemoryNode([
        #                         bt_ros.MoveLineToPoint(self.tactics.goldenium_1_PREgrab_pos, "move_client"),
        #                         bt_ros.MoveLineToPoint(self.tactics.goldenium_2_PREgrab_pos, "move_client"),
        #                         bt_ros.StartCollectGoldenium("manipulator_client"),

        #                         bt.ParallelWithMemoryNode([
        #                             bt_ros.MoveLineToPoint(self.tactics.goldenium_grab_pos, "move_client"),
        #                             bt_ros.CheckLimitSwitchInf("manipulator_client")
        #                         ], threshold=1),

        #                         bt_ros.GrabGoldeniumAndHoldUp("manipulator_client"),
        #                         bt.ActionNode(lambda: self.score_master.add("GOLDENIUM")),
        #                         bt.ActionNode(lambda: self.score_master.reward("GRAB_GOLDENIUM_BONUS")),
        #                     ])

        move_to_goldenium_prepose = bt.SequenceWithMemoryNode([
                                        bt_ros.MoveLineToPoint(self.tactics.goldenium_back_rot_pose, "move_client"),
                                        bt_ros.MoveLineToPoint(self.tactics.scales_goldenium_PREpos, "move_client")
                                    ])

        unload_goldenium = bt.SequenceWithMemoryNode([
                                bt.ConditionNode(self.is_scales_landing_free),
                                bt.SequenceWithMemoryNode([
                                    bt_ros.MoveLineToPoint(self.tactics.scales_goldenium_pos + np.array([0, -0.05, 0]), "move_client"),
                                    bt.ActionNode(lambda: self.score_master.unload("SCALES")),
                                    bt_ros.SetManipulatortoWall("manipulator_client"),
                                    bt_ros.MoveLineToPoint(self.tactics.scales_goldenium_pos, "move_client"),
                                    bt_ros.UnloadGoldenium("manipulator_client"),
                                ])
                            ])

        self.tree = bt.SequenceWithMemoryNode([
                                                red_cell_puck,
                                                green_cell_puck,
                                                blue_cell_puck,
                                                finish_move_blunium_and_push,
                                                approach_acc,
                                                push_unload_first_in_acc,
                                                unload_acc,
                                                collect_goldenium,
                                                move_to_goldenium_prepose,
                                                unload_goldenium,
                                                ])


class BlindStrategy(Strategy):
    def __init__(self, side):
        super(BlindStrategy, self).__init__()

        if side == SideStatus.PURPLE:
            self.param = "purple_side"
            self.side_sign = -1
        elif side == SideStatus.YELLOW:
            self.param = "yellow_side"
            self.side_sign = 1

        red_cell_puck = bt.SequenceWithMemoryNode([
                            bt_ros.MoveLineToPoint(self.first_puck_landing, "move_client"),
                            bt.FallbackWithMemoryNode([
                                bt.SequenceWithMemoryNode([
                                    bt_ros.BlindStartCollectGround("manipulator_client"),
                                    bt.ActionNode(lambda: self.score_master.add("REDIUM")),  # FIXME: color is undetermined without camera!
                                    bt.ParallelWithMemoryNode([
                                        bt_ros.CompleteCollectGround("manipulator_client"),
                                        bt_ros.MoveLineToPoint(self.first_puck_landing_finish, "move_client"),
                                    ], threshold=2),
                                ]),
                                bt.ParallelWithMemoryNode([
                                    bt_ros.SetManipulatortoWall("manipulator_client"),
                                    bt_ros.MoveLineToPoint(self.first_puck_landing_finish, "move_client"),
                                ], threshold=2)
                            ]),
                        ])

        green_cell_puck = bt.SequenceWithMemoryNode([
                            bt_ros.MoveLineToPoint(self.second_puck_landing, "move_client"),
                            bt.FallbackWithMemoryNode([
                                bt.SequenceWithMemoryNode([
                                    bt_ros.BlindStartCollectGround("manipulator_client"),
                                    bt.ActionNode(lambda: self.score_master.add("REDIUM")),  # FIXME: color is undetermined without camera!
                                    bt.ParallelWithMemoryNode([
                                        bt_ros.CompleteCollectGround("manipulator_client"),
                                        bt_ros.MoveLineToPoint(self.third_puck_landing, "move_client"),
                                    ], threshold=2),
                                ]),
                                bt.ParallelWithMemoryNode([
                                    bt_ros.SetManipulatortoWall("manipulator_client"),
                                    bt_ros.MoveLineToPoint(self.third_puck_landing, "move_client"),
                                ], threshold=2)
                            ])
                        ])

        blue_cell_puck = bt.SequenceWithMemoryNode([
                            bt.FallbackWithMemoryNode([
                                bt.SequenceWithMemoryNode([
                                    bt_ros.BlindStartCollectGround("manipulator_client"),
                                    bt.ActionNode(lambda: self.score_master.add("GREENIUM")),  # FIXME: color is undetermined without camera!
                                    bt.ParallelWithMemoryNode([
                                        bt_ros.CompleteCollectGround("manipulator_client"),
                                        bt_ros.MoveLineToPoint(self.blunium_collect_PREpos, "move_client"),
                                    ], threshold=2),
                                ]),
                                bt.ParallelWithMemoryNode([
                                    bt_ros.SetManipulatortoUp("manipulator_client"),  # FIXME when adding chaos
                                    bt_ros.MoveLineToPoint(self.blunium_collect_PREpos, "move_client"),
                                ], threshold=2)
                            ])
                        ])

        move_and_collect_blunium = bt.SequenceWithMemoryNode([
                                        # bt_ros.MoveLineToPoint(self.tactics.blunium_collect_PREpos, "move_client"),
                                        bt_ros.StartCollectBlunium("manipulator_client"),
                                        bt.ParallelWithMemoryNode([
                                            bt_ros.MoveLineToPoint(self.blunium_collect_pos, "move_client"),
                                            bt_ros.CheckLimitSwitchInfLong("manipulator_client")
                                        ], threshold=1),  # CheckLimitSwitchInf
                                        bt_ros.MoveLineToPoint(self.blunium_collect_pos_side, "move_client"),
                                        bt_ros.MoveLineToPoint(self.blunium_collect_pos + np.array([0, 0.04, 0]), "move_client"),  # FIXME
                                        bt_ros.FinishCollectBlunium("manipulator_client"),
                                        bt.ActionNode(lambda: self.score_master.add("BLUNIUM")),
                                        bt_ros.MainSetManipulatortoGround("manipulator_client")
                                    ])

        approach_acc = bt.SequenceWithMemoryNode([
                            bt_ros.MoveLineToPoint(self.blunium_get_back_pose, "move_client"),
                            bt_ros.MoveLineToPoint(self.accelerator_PREunloading_pos, "move_client"),  # FIXME try Arc
                            bt_ros.SetSpeedSTM([0, -0.1, 0], 0.9, "stm_client")
                        ])

        collect_unload_first_in_acc = bt.SequenceWithMemoryNode([
                                    bt_ros.StepperUp("manipulator_client"),  # FIXME do we need to do that? NO if all 7 pucks inside
                                    bt_ros.UnloadAccelerator("manipulator_client"),
                                    bt.ActionNode(lambda: self.score_master.unload("ACC")),
                                    bt.ActionNode(lambda: self.score_master.reward("UNLOCK_GOLDENIUM_BONUS"))
                                ])

        unload_acc = bt.SequenceNode([
                        bt.FallbackNode([
                            bt.ConditionNode(self.is_robot_empty),
                            bt.SequenceWithMemoryNode([
                                bt_ros.UnloadAccelerator("manipulator_client"),
                                bt.ActionNode(lambda: self.score_master.unload("ACC")),
                            ])
                        ]),
                        bt.ConditionNode(self.is_robot_empty_1)
                    ])

        collect_goldenium = bt.SequenceWithMemoryNode([
                                bt_ros.Delay500("manipulator_client"),
                                # bt_ros.MoveLineToPoint(self.tactics.goldenium_1_PREgrab_pos, "move_client"),
                                bt_ros.MoveLineToPoint(self.goldenium_2_PREgrab_pos, "move_client"),
                                bt_ros.StartCollectGoldenium("manipulator_client"),

                                bt.ParallelWithMemoryNode([
                                    bt_ros.MoveLineToPoint(self.goldenium_grab_pos, "move_client"),
                                    bt_ros.CheckLimitSwitchInfLong("manipulator_client")
                                ], threshold=1)
                            ])

        move_to_goldenium_prepose = bt.SequenceWithMemoryNode([
                                        bt_ros.MoveLineToPoint(self.goldenium_back_pose, "move_client"),
                                        bt_ros.GrabGoldeniumAndHoldUp("manipulator_client"),
                                        bt.ActionNode(lambda: self.score_master.add("GOLDENIUM")),
                                        bt.ActionNode(lambda: self.score_master.reward("GRAB_GOLDENIUM_BONUS")),

                                        # bt_ros.MoveLineToPoint(self.tactics.goldenium_back_rot_pose, "move_client"),
                                        bt_ros.MoveLineToPoint(self.scales_goldenium_PREpos, "move_client")
                                    ])

        unload_goldenium = bt.SequenceWithMemoryNode([
                                bt.ConditionNode(self.is_scales_landing_free),
                                bt.SequenceWithMemoryNode([
                                    bt_ros.MoveLineToPoint(self.scales_goldenium_pos + np.array([0, -0.01, 0]), "move_client"),
                                    bt.ActionNode(lambda: self.score_master.unload("SCALES")),
                                    bt_ros.SetManipulatortoWall("manipulator_client"),
                                    bt_ros.GrabGoldeniumAndHoldUp("manipulator_client"),
                                    bt_ros.SetManipulatortoWall("manipulator_client"),
                                    bt_ros.GrabGoldeniumAndHoldUp("manipulator_client"),
                                    bt_ros.MoveLineToPoint(self.scales_goldenium_pos, "move_client"),
                                    bt_ros.UnloadGoldenium("manipulator_client"),
                                    bt_ros.SetManipulatortoUp("manipulator_client")
                                ])
                            ])

        self.tree = bt.SequenceWithMemoryNode([
                                                red_cell_puck,
                                                green_cell_puck,
                                                blue_cell_puck,
                                                move_and_collect_blunium,
                                                approach_acc,
                                                collect_unload_first_in_acc,
                                                unload_acc,
                                                collect_goldenium,
                                                move_to_goldenium_prepose,
                                                unload_goldenium,
                                                ])


class OptimalStrategy(Strategy):
    def __init__(self, side):
        super(OptimalStrategy, self).__init__()

        if side == SideStatus.PURPLE:
            self.param = "purple_side"
            self.side_sign = -1
        elif side == SideStatus.YELLOW:
            self.param = "yellow_side"
            self.side_sign = 1

        rospy.sleep(15)
        self.tree = bt.FallbackWithMemoryNode([
                        bt.SequenceNode([
                            bt.ConditionNode(self.is_observed),
                            CollectChaos(self.known_chaos_pucks.get(), "move_client")
                        ]),
                        bt.ConditionNode(lambda: bt.Status.RUNNING)
                    ])


class GreedyStrategy(Strategy):
    def __init__(self):
        super(GreedyStrategy, self).__init__()
