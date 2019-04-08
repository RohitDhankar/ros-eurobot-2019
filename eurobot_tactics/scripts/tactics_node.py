#!/usr/bin/env python
# coding: utf-8
import rospy
import numpy as np
import tf2_ros
from tf.transformations import euler_from_quaternion
from visualization_msgs.msg import MarkerArray
from std_msgs.msg import String
from threading import Lock
from manipulator import Manipulator
from tactics_math import *
from core_functions import cvt_local2global

# from geometry_msgs.msg import Twist
# from std_msgs.msg import Int32MultiArray


"""

THIS VERSION CORRECTLY PASSES ALL TESTS USING and COLLECTs ONE BLUE PUCK LAST


This algorithm knows nothing about obstacles and etc, it just generates sorted list of options.
And path-planner will choose from these options according to obstacles around

TODO:
    - clockwise approaching in order to keep camera view open
    - FIXME path_planner should decide which puck to collect and to remove from known
    - in case we parse only first frame and while collecting pucks robot moves some of them, applying sort func is useless 
    - Alexey need to parse particular local zones
    - add check if there are more than 4 pucks in zone
    - add approach_immidiately flag
    - if BT interrupts procedure of collecting pucks, will it calculate landings again?
4 in chaos zone
3 periodic table
6 wall
3 wall
1 ramp

Input: list of n coordinates of pucks, that belong to one local group

Receiving coords from camera each 2-3 seconds
Each time coords are received we call function callback which compares currently known coords and newly received ones
If difference between newly received and known are within accuracy level (threshold), do nothing, else update known coords

Inside:
    - calculates the convex hull of these points
    - calculates inner angles and sorts them
    - calculates bissectrisa of the angle and adds offset
    -
"""


class TacticsNode:
    def __init__(self):
        rospy.init_node('tactics_node', anonymous=True)

        # TF
        self.tfBuffer = tf2_ros.Buffer()
        self.tfListener = tf2_ros.TransformListener(self.tfBuffer)
        self.mutex = Lock()

        self.robot_name = rospy.get_param("robot_name")  # "secondary_robot"

        self.critical_angle = np.pi * 2/3
        # self.critical_angle = rospy.get_param("critical_angle")

        self.red_zone_coords = np.array([0.3, 0.6, -np.pi/3])
        self.approach_dist = rospy.get_param("approach_dist")  # meters, distance from robot to puck where robot will try to grab it
        self.approach_dist = np.array(self.approach_dist)
        
        self.drive_back_dist = rospy.get_param("drive_back_dist")  # 0.04
        self.drive_back_dist = np.array(self.drive_back_dist)

        self.approach_vec = np.array([-1*self.approach_dist, 0, 0])  # 0.11
        self.drive_back_vec = np.array([-1*self.drive_back_dist, 0, 0])

        self.coords_threshold = rospy.get_param("coords_threshold")  # meters, this is variance of detecting pucks coords using camera, used in update

        self.scale_factor = rospy.get_param("scale_factor")  # used in calculating outer bissectrisa for hull's angles
        self.scale_factor = np.array(self.scale_factor)
        self.RATE = rospy.get_param("RATE")

        self.robot_coords = np.zeros(3)
        self.active_goal = None
        self.goal_landing = None
        self.pucks_inside = 0  # to preliminary calculate our score
        self.pucks_unloaded = 0

        self.sorted_chaos_landings = np.array([])
        self.known_chaos_pucks = np.array([])  # (x, y, id, r, g, b)

        self.operating_state = 'waiting for command'
        self.is_finished = False
        self.is_puck_sucked = False
        self.is_puck_collected = False

        self.cmd_id = None
        self.cmd_type = None

        # publishers
        self.move_command_publisher = rospy.Publisher('move_command', String, queue_size=10)
        self.stm_command_publisher = rospy.Publisher('stm_command', String, queue_size=1)
        self.response_publisher = rospy.Publisher("response", String, queue_size=10)

        rospy.sleep(2)

        self.timer = None

        self.manipulator = Manipulator()

        if self.robot_name == "main_robot":
            if not self.manipulator.calibrate_big():
                return

        if self.robot_name == "secondary_robot":
            if not self.manipulator.calibrate_small():
                return
            rospy.sleep(2)

        # coords are published as markers in one list according to 91-92 undistort.py
        rospy.Subscriber("/pucks", MarkerArray, self.chaos_pucks_coords_callback, queue_size=1)
        rospy.Subscriber("cmd_tactics", String, self.tactics_callback, queue_size=1)
        rospy.Subscriber("response", String, self.response_callback, queue_size=10)

    def chaos_pucks_coords_callback(self, data):
        """
        implement comparing with threshold,
        if newly received coord differs from old known one less than threshold level,
        than ignore it and continue collecting pucks.
        Else change coord of that puck and recalculate

        In first step we just write received coords to list of known pucks,
        in further steps we compare two lists and decide whether to update it or ignore

        :param self:
        :param data:
        :return:
        """
        self.mutex.acquire()

        if len(self.known_chaos_pucks) == 0:
            new_observation_pucks = [[marker.pose.position.x, marker.pose.position.y, marker.id, marker.color.r, marker.color.g, marker.color.b] for marker in data.markers]
            # [(0.95, 1.1, 3, 0, 0, 1), ...] - blue, id=3  IDs are not guaranteed to be the same from frame to frame
            print('TN -- new_observation_pucks')
            print(new_observation_pucks)

            try:
                self.known_chaos_pucks = np.array(new_observation_pucks)
                print("known")
                print(self.known_chaos_pucks)
            except Exception:  # FIXME
                print("list index out of range - no visible pucks on the field ")
        # else:
        #     self.compare_to_update_or_ignore(new_observation_pucks)  # in case robot accidentally moved some of pucks

        self.mutex.release()

    # noinspection PyTypeChecker
    # def tactics_callback(self, data):
    #
    #     self.mutex.acquire()
    #
    #     if self.timer is not None:
    #         self.timer.shutdown()
    #
    #     # self.parse_and_update_active_cmd(data)
    #     rospy.loginfo("")
    #     rospy.loginfo("=====================================")
    #     rospy.loginfo("TN: NEW CMD:\t" + str(data.data))
    #     rospy.loginfo("=====================================")
    #     rospy.loginfo("")
    #
    #     data_split = data.data.split()
    #     self.cmd_id = data_split[0]
    #     self.cmd_type = data_split[1]
    #
    #     self.timer = rospy.Timer(rospy.Duration(1.0 / self.RATE), self.timer_callback)
    #
    #     # FIXME There is a time delay for coords from camera to come
    #     self.mutex.release()

    # noinspection PyUnusedLocal
    # def timer_callback(self, event):
    #     """
    #     When BT publishes command something like "collect atoms in Chaos Zone", we start calculating and updating configuration of pucks
    #     :param event: cmd_type can be one of these:
    #     - collect_chaos
    #     - if in chaos taken blue - put it separately
    #     - take_from_wall_and_hold_above (
    #     - take_goldenium_and_hold_middle
    #     - collect_accel_blue (diff height, maybe we need to hold it up for a while)
    #     - skip
    #     :return:
    #     """
    #
    #     if self.cmd_type == "collect_chaos":
    #         if len(self.known_chaos_pucks) > 0:
    #             # print("inside timer: collect chaos and pucks > 0")
    #             self.collect_chaos()
    #         else:
    #             print("NO VISIBLE PUCKS ON THE FIELD")
    #             self.completely_stop()
    #
    #     elif self.cmd_type == "collect_chaos_and_unload":
    #         if len(self.known_chaos_pucks) > 0:
    #             self.collect_chaos()
    #         elif self.pucks_inside == 4:
    #             self.unload_pucks_in_red()
    #         elif self.pucks_inside == 0 and self.pucks_unloaded == 4:
    #             print("pucks unloaded")
    #             self.completely_stop()
    #
    #     else:
    #         # print("cmd_type is ", self.cmd_type)
    #         print("nothing was commanded")
    #         self.completely_stop()

    def collect_chaos(self):
        """
        0. Get the closest to robot landing from the list
        1. Approach it
        2. Grab and load it
        3. Remove from list of known
        4. Add to list of collected and count points TODO

        we append id of that puck to list of collected pucks and remove it from list of pucks to be collected.
        :return:
        """
        if self.operating_state == 'waiting for command':
            rospy.loginfo(self.operating_state)
            self.operating_state = 'approaching nearest PRElanding'
            rospy.loginfo(self.operating_state)

            while not self.update_coords():
                rospy.sleep(0.05)

            self.known_chaos_pucks = calculate_pucks_configuration(self.robot_coords, self.known_chaos_pucks, self.critical_angle)  # now [(0.95, 1.1, 3, 0, 0, 1), ...]
            self.sorted_chaos_landings = calculate_landings(self.robot_coords, self.known_chaos_pucks, self.approach_vec, self.scale_factor, self.approach_dist)
            self.goal_landing = self.sorted_chaos_landings[0]

            prelanding = cvt_local2global(self.drive_back_vec, self.goal_landing)
            self.active_goal = prelanding
            self.is_finished = False
            cmd = self.compose_command(self.active_goal, cmd_id='approach_nearest_PRElanding', move_type='move_line')
            self.move_command_publisher.publish(cmd)

        if self.operating_state == 'approaching nearest PRElanding' and self.is_finished:
            self.operating_state = 'nearest PRElanding approached'
            rospy.loginfo(self.operating_state)
            self.active_goal = None

        if self.operating_state == 'nearest PRElanding approached':
            self.operating_state = 'approaching nearest LANDING'
            rospy.loginfo(self.operating_state)
            self.active_goal = self.goal_landing
            self.is_finished = False
            cmd = self.compose_command(self.active_goal, cmd_id='approach_nearest_LANDING', move_type='move_line')
            self.move_command_publisher.publish(cmd)

        if self.operating_state == 'approaching nearest LANDING' and self.is_finished:
            self.operating_state = 'sucking puck'
            rospy.loginfo(self.operating_state)
            if self.robot_name == "secondary_robot":
                self.is_puck_sucked = self.manipulator.grab_and_suck_small()
            self.is_finished = False

        if self.operating_state == 'sucking puck' and self.is_puck_sucked:
            rospy.sleep(0.5)  # FIXME
            self.operating_state = 'driving back for safety'
            rospy.loginfo(self.operating_state)
            prelanding = cvt_local2global(self.drive_back_vec, self.goal_landing)
            self.active_goal = prelanding
            cmd = self.compose_command(self.active_goal, cmd_id='driving_back_for_safety', move_type='move_line')
            self.move_command_publisher.publish(cmd)

        if self.operating_state == 'driving back for safety' and self.is_finished:
            self.operating_state = 'finishing collecting puck'
            rospy.loginfo(self.operating_state)
            self.goal_landing = None
            self.is_finished = False
            # self.imitate_manipulator()
            # if self.robot_name == "main_robot":
            #     self.is_puck_collected = self.manipulator.finish_collect_big()
            if self.robot_name == "secondary_robot":
                self.is_puck_collected = self.manipulator.finish_collect_small()

        if self.operating_state == 'finishing collecting puck' and self.is_puck_collected:
            self.operating_state = 'puck successfully collected'
            rospy.loginfo("Wohoo! " + str(self.known_chaos_pucks[0]) + " " + str(self.operating_state))
            self.pucks_inside += 1
            print(" ")
            print("now delete puck", self.known_chaos_pucks[0])
            print(" ")
            self.known_chaos_pucks = np.delete(self.known_chaos_pucks, 0, axis=0)
            rospy.loginfo('TN: pucks left: ' + str(len(self.known_chaos_pucks)))
            rospy.loginfo('TN: pucks Inside: ' + str(self.pucks_inside))

        if self.operating_state == 'puck successfully collected':
            self.is_puck_collected = False
            self.active_goal = None
            self.sorted_chaos_landings = None
            self.is_puck_sucked = False
            self.operating_state = 'waiting for command'
            rospy.loginfo(self.operating_state)

    # def unload_pucks_in_red(self):
    #     if self.operating_state == "waiting for command":
    #         self.operating_state = "moving to red zone"
    #         rospy.loginfo(self.operating_state)
    #         self.is_finished = False
    #         self.active_goal = self.red_zone_coords
    #         cmd = self.compose_command(self.active_goal, cmd_id='move_to_red_zone', move_type='move_line')
    #         self.move_command_publisher.publish(cmd)
    #
    #     if self.operating_state == "moving to red zone" and self.is_finished:
    #         self.operating_state = "start unloading"
    #         rospy.loginfo(self.operating_state)
    #         self.is_finished = False
    #         self.manipulator.release_small()
    #         self.pucks_unloaded = 4
    #         self.pucks_inside = 0

    # def response_callback(self, data):
    #     """
    #     here when robot reaches the goal MotionPlannerNode will publish in response topic "finished" and in this code
    #     callback_response will fire and change self.is_finished to True
    #     :param data:
    #     :return:
    #     """
    #     if data.data == 'finished':  # TODO change so that response is marked by cmd_id ''
    #         self.is_finished = True

    # @staticmethod
    # def compose_command(landing, cmd_id, move_type):
    #     x, y, theta = landing[0], landing[1], landing[2]
    #     command = str(cmd_id)
    #     command += ' '
    #     command += str(move_type)
    #     command += ' '
    #     command += str(x)
    #     command += ' '
    #     command += str(y)
    #     command += ' '
    #     command += str(theta)
    #     rospy.loginfo("=============================")
    #     rospy.loginfo('TN: NEW COMMAND COMPOSED')
    #     rospy.loginfo(command)
    #     rospy.loginfo("=============================")
    #     return command

    # def imitate_manipulator(self):
    #     rospy.loginfo('TN: puck collected by imitator!!')
    #     self.is_puck_collected = True

    # def completely_stop(self):
    #     self.timer.shutdown()
    #     rospy.loginfo("TN -- Robot has completely stopped")
    #     rospy.sleep(1.0 / 40)
    #     self.operating_state = 'waiting for command'
    #     rospy.loginfo(self.operating_state)
    #     print(" ")
    #     print(" ")
    #     self.response_publisher.publish(self.cmd_id + " finished")

    def update_coords(self):
        try:
            trans = self.tfBuffer.lookup_transform('map', self.robot_name, rospy.Time())
            q = [trans.transform.rotation.x,
                 trans.transform.rotation.y,
                 trans.transform.rotation.z,
                 trans.transform.rotation.w]
            angle = euler_from_quaternion(q)[2] % (2 * np.pi)

            self.robot_coords = np.array([trans.transform.translation.x, trans.transform.translation.y, angle])
            # rospy.loginfo("TN: Robot coords:\t" + str(self.robot_coords))
            return True
        except (tf2_ros.LookupException, tf2_ros.ConnectivityException, tf2_ros.ExtrapolationException) as msg:
            rospy.logwarn(str(msg))
            return False


if __name__ == "__main__":
    tactics = TacticsNode()
    rospy.spin()
