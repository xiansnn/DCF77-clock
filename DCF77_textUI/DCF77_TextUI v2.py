import uasyncio

from DCF77.DCF77_decoder import *
from DCF77.local_time_calendar_IRQ import LocalTimeCalendar

from lib_pico.ST7735_TextUIv2 import *
from lib_pico.widget import Scale

TONE_GPIO = const(7) # the GPIO where DCF signal is received by MCU


class DCF_Display_TextUI():
    """
Defines how the DCF decoder displays time, calendar and status on the ST7735 LCD module
"""
    def __init__(self):
        self.display = TFT_display()

        self.title_frame = self.display.add_frame("title",(0,0),(50,9),
                                                  background_color=TFT.BLACK, top_border=1)
        self.time_zone = self.display.add_frame("time_zone",(51,0),(100,9),
                                                   background_color=TFT.BLACK,   left_border=01, top_border=1 )       
        self.signal_status_frame = self.display.add_frame("signal", (112,0),(119,9),
                                                   background_color=TFT.BLACK,   left_border=1, top_border=1 )
        self.time_status_frame = self.display.add_frame("time_status",(120,0),(127,9),
                                                    background_color=TFT.BLACK,   left_border=1, top_border=1 )
        self.date_frame = self.display.add_frame("date",(0,30),(127,50), font_size_factor=(2,2),
                                                 background_color=TFT.BLACK,     left_border=5, top_border=1 )
        self.time_frame = self.display.add_frame("time",(0,51),(127,99), font_size_factor=(3,5),
                                                 background_color=TFT.BLACK,     left_border=1, top_border=8 )
        self.second_scale_frame = self.display.add_frame("second_scale",(0,110),(127,120),
                                                   background_color=TFT.BLACK,   left_border=01, top_border=3 )
        self.scale = Scale(self.second_scale_frame , (4,8),120, TFT.YELLOW )
        
        self.title_frame.write_text("DCF77", TFT.YELLOW)
        self.time_status_color = TFT.WHITE

        
    def update_time_status(self, event, new_status, message=""):
        if new_status == TIME_INIT:
            status_symbol = BLANK
            self.time_status_color = TFT.GRAY
        elif new_status == OUT_OF_SYNC:
            status_symbol = BLANK
            self.time_status_color = TFT.RED
        elif new_status == SYNC_IN_PROGRESS:
            status_symbol = BLANK
            self.time_status_color = TFT.GRAY
        elif new_status == SYNC_FAILED:
            status_symbol = BLANK
            self.time_status_color = TFT.ORANGE
        elif new_status == SYNC:
            status_symbol = BLANK
            self.time_status_color = TFT.LIME
        self.time_status_frame.write_char(status_symbol, self.time_status_color, append=False)

    def update_signal_status(self, current_frame, event, new_status):
        if current_frame != None:
            data = current_frame[-1]
            rank = len(current_frame)-1
            self.signal_status_frame.write_char(data, self.time_status_color, append=False)
        else:
            pass
        
    def update_seconds(self, seconds):
        if seconds == 0:
             self.second_scale_frame.erase_frame()
        self.scale.set_value(seconds)
        
    def update_date_and_time(self, clock_update):
        week_day , day, month, year, hours, minutes, seconds, time_zone = clock_update
        self.date_frame.write_text(f"{week_day:>3s}-{day:0>2d}-{month:3s}",TFT.YELLOW)
        self.time_frame.write_text(f" {hours:0>2d}:{minutes:0>2d}",TFT.YELLOW)
        self.time_zone.write_text(f"GMT{time_zone:<+3d}",TFT.YELLOW)
        self.second_scale_frame.erase_frame()
        self.scale.set_value(seconds)



################### test ############################ 
# init main tasks
display = DCF_Display_TextUI()
local_clock_calendar = LocalTimeCalendar(display)
DCF_decoder = DCF_Decoder(TONE_GPIO, local_clock_calendar, display)

# setup coroutines
DCF_frame_coroutine = DCF_decoder.frame_decoder()
DCF_signal_monitor_coroutine = DCF_decoder.DCF_signal_monitoring()
local_time_coroutine = local_clock_calendar.next_second()

#start coroutines
scheduler = uasyncio.get_event_loop()

scheduler.create_task(local_time_coroutine)
scheduler.create_task(DCF_signal_monitor_coroutine)
scheduler.create_task(DCF_frame_coroutine)

scheduler.run_forever()
############""
