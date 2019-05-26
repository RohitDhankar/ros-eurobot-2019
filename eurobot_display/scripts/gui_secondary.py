#!/usr/bin/env python
import rospy
from std_msgs.msg import String
import numpy as np
from Tkinter import *
import tf2_ros
from tf.transformations import euler_from_quaternion
from visualization_msgs.msg import MarkerArray

SIDE_COLORS = np.array([[255, 255, 0],  # yellow
                        [255, 0, 255],  # purple
                        [124, 252, 0]])  # green

HEARTBEAT = np.array([[255, 0, 0],  # red
                      [124, 252, 0]])  # green

class Prediction:
    def __init__(self):

        self.puck_points = {
            "REDIUM_ON_RED": 6,
            "REDIUM_ON_GREEN": 1,
            "REDIUM_ON_BLUE": 1,

            "GREENIUM_ON_GREEN": 6,
            "GREENIUM_ON_RED": 1,
            "GREENIUM_ON_BLUE": 1,

            "BLUNIUM_ON_BLUE": 6,
            "BLUNIUM_ON_RED": 1,
            "BLUNIUM_ON_GREEN": 1,

            "UNDEFINED_ON_BLUE": 1,
            "UNDEFINED_ON_MIDDLE": 6,

            "GOLDENIUM_ON_CELLS": 6,

            "REDIUM_ON_ACC": 10,
            "GREENIUM_ON_ACC": 10,
            "BLUNIUM_ON_ACC": 10,

            "UNLOCK_GOLDENIUM_BONUS": 10,
            "GRAB_GOLDENIUM_BONUS": 20,

            "REDIUM_ON_SCALES": 4,
            "GREENIUM_ON_SCALES": 8,
            "BLUNIUM_ON_SCALES": 12,
            "GOLDENIUM_ON_SCALES": 24,
        }

    def get_points(self, key):
        return self.puck_points.get(key)


class App:
    def __init__(self, master):
        self.master = master
        self.predict = Prediction()
        self.tfBuffer = tf2_ros.Buffer()
        self.tfListener = tf2_ros.TransformListener(self.tfBuffer)
        self.first_update = True
        self.secondary_coords_array = np.array([0, 0, 0])
        self.signal_color = HEARTBEAT[0]
        
        # Master page
        frame = Frame(master, bg="white", colormap="new")
        frame.pack()

        # Secondary block
        self.frame5 = Frame(frame, bg="white", colormap="new")
        self.frame5.pack(side="top")

        # Secondary config block
        self.frame6 = Frame(frame, bg="white", colormap="new")
        self.frame6.pack(side="top")

        # Secondary block wire status
        self.frame8 = Frame(self.frame5, bg="white", colormap="new")
        self.frame8.pack(side="left")

        # Secondary block side status
        self.frame9 = Frame(self.frame5, bg="white", colormap="new")
        self.frame9.pack(side="right")

        # --------------------------------------------------

        # Heartbeat config
        self.heartbeat = Label(self.frame6, bg="red", height=1, width=3, font=("Helvetica", 10))
        self.heartbeat.pack(side="top")

        # secondary WIRE config
        self.secondary_start_status = StringVar()
        self.secondary_start_status.set("Waiting")
        self.secondary_wire_frame = Label(self.frame8, bg="gray", height=2, width=9, font=("Helvetica", 40), textvariable=self.secondary_start_status)
        self.secondary_wire_frame.pack(side="right")
        # .pack() need to be a separate line, otherwise will get Attribute Error when applying config method

        # secondary SIDE config
        self.secondary_side_status = StringVar()
        self.secondary_side_frame = Label(self.frame9, bg="gray", height=2, width=9, font=("Helvetica", 40), textvariable=self.secondary_side_status)
        self.secondary_side_status.set("Side")
        self.secondary_side_frame.pack(side="left")

        # secondary STRATEGY config
        self.secondary_strategy_status = StringVar()
        self.secondary_strategy_frame = Label(self.frame9, bg="green", height=2, width=9, font=("Helvetica", 40), textvariable=self.secondary_strategy_status)
        self.secondary_strategy_status.set("Strategy")
        self.secondary_strategy_frame.pack(side="top")


        # Secondary block config: name, coords, score
        self.secondary_coords = StringVar()
        self.secondary_coords.set(self.secondary_coords_array)

        self.score_secondary = IntVar()
        self.score_secondary.set(0)

        # Label(frame, bg="white", height=2, width=13, font=("Helvetica", 60), text="Secondary").pack(side="top")
        self.secondary_coords_frame = Label(self.frame6, bg="white", height=1, width=16, font=("Helvetica", 80),
                                            textvariable=self.secondary_coords)
        self.secondary_coords_frame.pack(side="top")
        Label(self.frame6, bg="white", height=2, width=4, textvariable=self.score_secondary, font=("Helvetica", 150)).pack(side="top")

# ========================================================================

    def heartbeat_loop(self):

        if self.heartbeat["bg"] == '#%02x%02x%02x' % tuple(self.signal_color):  # "red"
            self.heartbeat.config(bg="white")  # "white"
            self.frame5.after(0, self.update_secondary_coords)
        else:
            self.heartbeat.config(bg='#%02x%02x%02x' % tuple(self.signal_color))  # "red"
        self.frame5.after(800, self.heartbeat_loop)

    def secondary_side_status_callback(self, data):
        if data.data == "1":
            self.secondary_side_status.set("YELLOW")
            self.secondary_side_frame.config(bg='#%02x%02x%02x' % tuple(SIDE_COLORS[0]))

        elif data.data == "0":
            self.secondary_side_status.set("PURPLE")
            self.secondary_side_frame.config(bg='#%02x%02x%02x' % tuple(SIDE_COLORS[1]))

        self.frame5.after(1000, self.update_secondary_coords)  # start loop  # FIXME

    def secondary_wire_status_callback(self, data):
        if data.data == "0":
            self.secondary_start_status.set("READY")
            self.secondary_wire_frame.config(bg="red")
        elif data.data == "1":
            self.secondary_start_status.set("GO!")
            self.secondary_wire_frame.config(bg='#%02x%02x%02x' % tuple(SIDE_COLORS[2]))

    def secondary_strategy_status_callback(self, data):
        if data.data == "0":
            self.secondary_strategy_status.set("0 STR")
        elif data.data == "1":
            self.secondary_strategy_status.set("1 STR")
        elif data.data == "2":
            self.secondary_strategy_status.set("2 STR")
    

    def secondary_score_callback(self, data):
        """

        :param data: REDIUM_ON_RED, BLUNIUM_ON_SCALES, UNLOCK_GOLDENIUM_BONUS
        :return:
        """
        points = self.predict.get_points(data.data)
        self.score_secondary.set(self.score_secondary.get() + int(points))

    def main_pucks_callback(self, data):

        try:
            new_observation_pucks = [[marker.pose.position.x,
                                      marker.pose.position.y,
                                      marker.id,
                                      marker.color.r,
                                      marker.color.g,
                                      marker.color.b] for marker in data.markers]

            if len(new_observation_pucks) > 8:
                self.signal_color = HEARTBEAT[1]

        except Exception:  # FIXME
            rospy.loginfo("list index out of range - no visible pucks on the field ")

    def update_secondary_coords(self):
        try:
            trans_secondary = self.tfBuffer.lookup_transform('map', "secondary_robot", rospy.Time(0))

            q_secondary = [trans_secondary.transform.rotation.x,
                           trans_secondary.transform.rotation.y,
                           trans_secondary.transform.rotation.z,
                           trans_secondary.transform.rotation.w]

            angle_secondary = euler_from_quaternion(q_secondary)[2] % (2 * np.pi)

            self.secondary_coords_array = np.array([trans_secondary.transform.translation.x,
                                              trans_secondary.transform.translation.y,
                                              angle_secondary])

            self.secondary_coords.set(('%.2f' % self.secondary_coords_array[0],
                                    '%.2f' % self.secondary_coords_array[1],
                                    '%.2f' % self.secondary_coords_array[2]))

            # return True

        except (tf2_ros.LookupException, tf2_ros.ConnectivityException, tf2_ros.ExtrapolationException) as msg:
            rospy.logwarn(str(msg))
            # return False


if __name__ == '__main__':
    rospy.init_node("display_node")
    root = Tk()
    root.title("Eurobot RESET")
    root.geometry("800x600")

    app = App(root)
    app.heartbeat_loop()

    rospy.Subscriber("score", String, app.secondary_score_callback)
    rospy.Subscriber("stm/start_status", String, app.secondary_wire_status_callback)
    rospy.Subscriber("stm/side_status", String, app.secondary_side_status_callback)
    rospy.Subscriber("stm/strategy_status", String, app.secondary_strategy_status_callback)
    rospy.Subscriber("/pucks", MarkerArray, app.main_pucks_callback, queue_size=1)

    rate = rospy.Rate(100)
    rospy.loginfo("Start display")

    def check():
        root.after(50, check)  # 50 stands for 50 ms.

    root.after(50, check)

    try:
        root.mainloop()
    except:
        print "you pressed control c"
        sys.exit(0)