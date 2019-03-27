import enum
import rospy
from std_msgs.msg import String

from termcolor import colored, cprint


class SideStatus(enum.Enum):
    YELLOW = 1
    PURPLE = 0


class BTController():
    def __init__(self, behavior_tree):
        self.side_status_subscriber = rospy.Subscriber("stm/side_status", String, self.side_status_callback)
        self.start_status_subscriber = rospy.Subscriber("stm/start_status", String, self.start_status_callback)

        self.start_counter = 0
        self.behavior_tree = behavior_tree

    def side_status_callback(self, data):
            if data.data == "1" and self.behavior_tree.side_status == SideStatus.PURPLE:
                cprint ("UPDATE SIDE TO " + colored("YELLOW", "yellow", attrs=['bold', 'blink']))
                self.behavior_tree.change_side(SideStatus.YELLOW)
            if data.data == "0" and self.behavior_tree.side_status == SideStatus.YELLOW:
                cprint ("UPDATE SIDE TO " + colored("PURPLE", "magenta", attrs=['bold', 'blink']))
                self.behavior_tree.change_side(SideStatus.PURPLE)

    def start_status_callback(self, data):
        if data.data == "1":
            self.behavior_tree.start()
            self.start_status_subscriber.unregister()
            self.side_status_subscriber.unregister()

        # if data.data == "1":
        #     self.start_counter += 1
        # else:
        #     self.start_counter = 0
        # if self.start_counter == 5:
        #     # TRY TO SHUTDOWN THE SUBSCRIBER
        #     self.behavior_tree.start()
        #     self.start_status_subscriber.unregister()
        #     self.side_status_subscriber.unregister()
