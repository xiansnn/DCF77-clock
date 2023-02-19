import uasyncio

from DCF77.DCF77_decoder import DCF_Decoder
from DCF77.local_time_calendar_IRQ import LocalTimeCalendar

TONE_GPIO = const(7) # the GPIO where DCF signal is received by MCU

SIGNAL_STATUS_TAB = const("")
TIME_STATUS_TAB   = const("\t\t")
LOCAL_TIME_TAB    = const("\t\t\t\t\t\t\t\t\t")


class DCF_Display_stub():
    def __init__(self):
        print("init DCF_Display_stub")
        
    def update_time_status(self, event, new_status, message=""):
        print(f"{TIME_STATUS_TAB}time_status\t-- ({event:^20s}) --> [{new_status:^20s}] : {message}")

    def update_signal_status(self, current_string, event, new_status):
        if current_string != None:
            data = current_string[-1]
            rank = len(current_string)-1
            print(f"{SIGNAL_STATUS_TAB}signal_status\t-- ({event:^20s}) --> [{new_status:^20s}] : Data[{rank:0>2d}] = {data}")
        else:
            print(f"{SIGNAL_STATUS_TAB}signal_status\t-- ({event:^20s}) --> [{new_status:^20s}] : No Data")
            
    def update_date_and_time(self, time_string):
        week_day , day, month, year, hours, minutes, seconds, time_zone = time_string
        print(f"{LOCAL_TIME_TAB}LocalTime:\t{week_day} {day} {month} 20{year}\t{hours:0>2d}:{minutes:0>2d}:{seconds:0>2d}\tzone:{time_zone}")

    def update_seconds(self, seconds):
        print(f"{LOCAL_TIME_TAB}{seconds:0>2d}")


################### test ############################ 
# init main tasks
display = DCF_Display_stub()
local_clock_calendar = LocalTimeCalendar(display)
DCF_decoder = DCF_Decoder(TONE_GPIO, local_clock_calendar, display)

# setup coroutines
DCF_frame_coroutine = DCF_decoder.frame_decoder()
DCF_signal_monitor_coroutine = DCF_decoder.DCF_signal_monitoring()
local_time_coroutine = local_clock_calendar.next_second()

#start coroutines
scheduler = uasyncio.get_event_loop()

scheduler.create_task(DCF_signal_monitor_coroutine)
scheduler.create_task(DCF_frame_coroutine)
scheduler.create_task(local_time_coroutine)

scheduler.run_forever()

