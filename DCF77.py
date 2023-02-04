import uasyncio, ustruct, time
from machine import Timer, Pin, Signal
from lib_pico.async_push_button import Button
from lib_pico.ST7735_TextUIv2 import *
from lib_pico.filter import PID, FilteredPID, clamp
from lib_pico.widget import Scale

from debug_utility.pulses import Probe
probe_gpio = 16
probe = Probe(probe_gpio)

import micropython
micropython.alloc_emergency_exception_buf(100)

TONE_GPIO = const(7) # the GPIO where DCF signal is received by MCU



class DCF_Display():
    """
Defines how the DCF decoder displays time, calendar and status on the ST7735 LCD module
"""
    def __init__(self):
        self.display = TFT_display()
        self.title_frame = self.display.add_frame("title",(0,0),(127,9),top_border=1)
        self.title_frame.write_text("     DCF77 TIME     ", TFT.YELLOW)
        self.time_status_frame = self.display.add_frame("time_status",(0,10),(127,19),
                                                    background_color=TFT.BLACK,   left_border=1, top_border=1 )
        self.signal_frame = self.display.add_frame("signal",(0,20),(127,29),
                                                   background_color=TFT.BLACK,   left_border=1, top_border=1 )
        self.date_frame = self.display.add_frame("date",(0,30),(127,50), font_size_factor=(2,2),
                                                 background_color=TFT.BLACK,     left_border=1, top_border=1 )
        self.time_frame = self.display.add_frame("time",(0,51),(127,99), font_size_factor=(3,5),
                                                 background_color=TFT.BLACK,     left_border=1, top_border=8 )
        self.second_scale_frame = self.display.add_frame("second_scale",(0,100),(127,115),
                                                   background_color=TFT.BLACK,   left_border=01, top_border=3 )
        self.scale = Scale(self.second_scale_frame , (4,8),120, TFT.YELLOW )
        self.second_frame = self.display.add_frame("second",(0,116),(127,127),
                                                   background_color=TFT.BLACK,   left_border=01, top_border=1 )
        
    def update_time_status(self, status, color):
        #         self.time_status_frame.write_text(f"{status:>20s}", color)
        self.time_status_frame.write_char(status, color)
    
    def update_signal_status(self, status, color):
        #         self.signal_frame.write_text(f"{status:>20s}", color)
        self.signal_frame.write_char(status, color)

    def update_date_and_time(self, time):
        self.date_frame.write_text(f"{time.week_day:>3s}-{time.day:0>2d}-{time.month:3s}",TFT.YELLOW)
        self.time_frame.write_text(f" {time.hours:0>2d}:{time.minutes:0>2d}",TFT.YELLOW)
        self.second_frame.write_text(f"{time.seconds:0>2d}s  20{time.year:0>2d}  zone:{time.time_zone:>4s}",TFT.GRAY)
        self.scale.set_value(time.seconds)




class StatusController():
    """
    Manages local time, DCF decoder status as a simplified statemachine:
    - update_xxxx are the methods that display time calendar and DCF signal status
    - other methods are the events that trig state transitions
    """
    # time status
    SYNC = BLANK
    OUT_OF_SYNC = "x"

    WAIT_END_OF_FRAME = "<"
    WAIT_NEW_FRAME = ">"

    FRAME_ERROR = "e"
    MISSING_DATA = "m"

    #signal status
    INIT = "."
    SIGNAL_LOST = "X"
    SIGNAL_RECEIVED = BLANK
    SIGNAL_LATE = "-"

    def __init__(self, display):
        self.display = display
        self.time_status_color = TFT.GRAY
        self.time_status = StatusController.WAIT_END_OF_FRAME
        self.signal_status = StatusController.INIT
        self.display.update_time_status(self.time_status, self.time_status_color)
        self.display.update_signal_status(self.signal_status, TFT.RED )
        

    # signal status management    
    def signal_received(self, data):
        if self.time_status == StatusController.OUT_OF_SYNC:
            self.init_frame_decoding()
        self.signal_status = StatusController.SIGNAL_RECEIVED
        self.display.update_signal_status(data, self.time_status_color)
    
    def signal_timeout(self):
        if (self.signal_status == StatusController.SIGNAL_LATE) :
            self.signal_status = StatusController.SIGNAL_LOST
            self.out_of_sync()
            self.display.update_signal_status(StatusController.SIGNAL_LOST, self.time_status_color)
        else :
            if self.signal_status != StatusController.SIGNAL_LOST:
                self.signal_status = StatusController.SIGNAL_LATE
                self.display.update_signal_status(StatusController.SIGNAL_LATE, self.time_status_color)

    # time status management
    def update_time_status(self, new_status, color):
        self.time_status = new_status
        self.time_status_color = color
        self.display.update_time_status(self.time_status, self.time_status_color)

        # entering new state
    def out_of_sync(self):
        self.update_time_status(StatusController.OUT_OF_SYNC, TFT.RED)
    def init_frame_decoding(self):   
        self.update_time_status(StatusController.WAIT_END_OF_FRAME, TFT.GRAY)        
    def start_frame_decoding(self):
        self.update_time_status(StatusController.WAIT_NEW_FRAME, TFT.YELLOW)
        self.update_time_status(StatusController.WAIT_END_OF_FRAME, TFT.YELLOW)
    def wait_new_frame(self):
        self.update_time_status(StatusController.WAIT_NEW_FRAME, TFT.YELLOW)
    def sync_failed(self, error):    
        self.update_time_status(error, TFT.ORANGE)
    def sync_done(self):
        self.update_time_status(StatusController.SYNC, TFT.GREEN)
        self.update_time_status(StatusController.WAIT_NEW_FRAME, TFT.GREEN)
        self.update_time_status(StatusController.WAIT_END_OF_FRAME, TFT.GREEN)

        # processing event
    def new_minute_received(self):
        if self.time_status != StatusController.WAIT_END_OF_FRAME:
            self.start_frame_decoding()
        else :
            self.wait_new_frame()               

    def frame_parity_error(self):
        self.sync_failed(StatusController.FRAME_ERROR)
        self.start_frame_decoding()
        
    def frame_incomplete(self):
        self.sync_failed(StatusController.MISSING_DATA)
        self.start_frame_decoding()
    

class DCF_Decoder():
    """ the DCF decoder algorithm, triggered by the DCF radio signal after
    being processed by electronic circuitry """
    def __init__(self, key_in_gpio, local_time, status_controller):
        self._DCF_clock_received = uasyncio.ThreadSafeFlag()
        self._DCF_frame_received = uasyncio.ThreadSafeFlag()
        Button("tone", key_in_gpio, pull=-1,
               interrupt_service_routine=self._DCF_clock_IRQ_handler,
               debounce_delay=80,
               active_HI=True, both_edge=True )
        self._time = local_time
        self._status_controller = status_controller
        self._current_string = ""
        self._frame = "" 
        self._DCF_signal_duration =0
        self._DCF_signal_is_high = True
        self._DCF_clock_received = uasyncio.ThreadSafeFlag()
   
    def _push(self, data):
        self._current_string += data
        self._status_controller.signal_received(data)
#         print(f"data:{data}, current_buffer:{len(self._current_string)},{self._current_string}")
        if data == "#" :
            self._frame = self._current_string
            self._current_string = ""
  
    def _DCF_clock_IRQ_handler(self, button):
        irq_state = machine.disable_irq()
        self._DCF_signal_duration = button.last_event_duration
        self._DCF_signal_is_high = button.is_pressed           
        if self._DCF_signal_is_high :
            # we check the previous low level duration:
            # - about 800ms means previous hi-level is 200ms (i.e. logic "1")
            # - about 900ms means previous hi-level is 100ms (i.e. logic "0")
            # - more than 1000ms means we've had a 1-second signal that means "next minute"
            # including 800ms or 900ms for the last parity 59th bit 
            if self._DCF_signal_duration >= 750 and self._DCF_signal_duration < 850 :
                self._push("1") # we record a logic "1" signal
            elif self._DCF_signal_duration >= 850 and self._DCF_signal_duration < 950 :
                self._push("0") # we record a logic "0" signal
            elif self._DCF_signal_duration >= 1750 and self._DCF_signal_duration < 1950 :
                if self._DCF_signal_duration < 1850 :
                    self._push("1")
                else :
                    self._push("0")
                self._push("#") # we record a "next minute" signal (coded by "#")
                self._DCF_frame_received.set()
   
        self._DCF_clock_received.set()
        machine.enable_irq(irq_state)     
        
    def _BCD_decoder(self, string):
        BCD_weight = [1, 2, 4, 8, 10, 20, 40, 80]
        value = 0
        for k in range(len(string)):
            value += BCD_weight[k]*int(string[k])
        return value
    
    def _frame_parity_is_valid(self):
        s0 = (self._frame[0]  == "0") # check start of frame, always "0"
        s1 = (self._frame[20] == "1") # check start of time encoding, always "1"
        p1 = (self._frame[21:29].count("1")%2 == 0) # check parity
        p2 = (self._frame[29:36].count("1")%2 == 0) # check parity
        p3 = (self._frame[36:59].count("1")%2 == 0) # check parity
        return (s0 and s1 and p1 and p2 and p3)        

    def _all_bits_received(self):
        return len(self._frame)==60
        
    async def frame_decoder(self):
        """ coroutine that decode DCF signal, triggered by the reception of End of Frame"""
        while True:
            await self._DCF_frame_received.wait()
            self._time.start_new_minute()
            if not self._all_bits_received():   
                self._status_controller.frame_incomplete()
            else:
                if not self._frame_parity_is_valid():
                    self._status_controller.frame_parity_error()
                else: # we have now, a full frame without reception error
                    time_zone_num = self._BCD_decoder(self._frame[17:19])
                    minutes = self._BCD_decoder(self._frame[21:28])
                    hours = self._BCD_decoder(self._frame[29:35])
                    day = self._BCD_decoder(self._frame[36:42])
                    week_day_num = self._BCD_decoder(self._frame[42:45])
                    month_num = self._BCD_decoder(self._frame[45:50])
                    year = self._BCD_decoder(self._frame[50:58])
                    self._time.update_time(ustruct.pack("6HB",
                         year, month_num, day, week_day_num, hours, minutes, time_zone_num))
                    self._status_controller.sync_done()

    async def DCF_signal_monitoring(self):
        while True:
            try:
                await uasyncio.wait_for_ms(self._DCF_clock_received.wait(), 4000)
                self._DCF_clock_received.clear()

            except uasyncio.TimeoutError:
#                 print("timeout")
                self._status_controller.signal_timeout()




class LocalTimeCalendar():
    """    The local clock/calendar, triggered by 1-second local timer    """
    def __init__(self, display):
        # G proportional gain of the PID corrector
        # Ti integration time constant of the PID corrector
        # Td derivative time constant of the PID corrector
        # Ts sampling time      
        self.pid=FilteredPID( Ts=1000, G=.55 , Ti=3000 , Td=10 , N=10) # values determined experimentally

        self._display = display
        self.year = 0
        self.month = "xxx"
        self._month_values = ["xxx","JAN","FEV","MAR","AVR","MAI","JUN","JUL","AOU","SEP","OCT","NOV","DEC"]
        self.day = 0
        self.week_day = "xxx"
        self._week_day_values = ["xxx","LUN","MAR","MER","JEU","VEN","SAM","DIM"]
        self.hours = 0
        self.minutes = 0
        self.seconds = 0
        self.time_zone = "xxx" #CET = +1, CEST = +2
        self._time_zone_values = ["GMT","CEST","CET"]
        # variables for the PID corrector in next_second coroutine
        self._last_time = 0
        self._current_delay = 10
 
    def update_time(self, time_pack):
        """
        When a DCF frame is received, the decoder packs a set of bites
        and this set is used to update the local clock
        """
        (year, month, day, week_day, hours, minutes, time_zone) = ustruct.unpack("6HB",time_pack)
        self.year = year
        self.month = self._month_values[month]
        self.day = day
        self.week_day = self._week_day_values[week_day]
        self.hours = hours
        self.minutes = minutes
        self.time_zone = self._time_zone_values[time_zone]
        self._display.update_date_and_time(self)

    def start_new_minute(self):
        """ method used when a "next minute" signal is received """
        self.minutes +=1
        self.seconds = 0
        self._display.second_scale_frame.erase_frame()
        self._display.update_date_and_time(self)
        
    def _next_hour(self):
        if self.hours==23:
            self.hours = 0
        else:
            self.hours +=1
            
    def _next_minute(self):
        if self.minutes==59:
            self.minutes = 0
            self._next_hour()
        else:
            self.minutes +=1
            
    async def next_second(self):
        """ coroutine triggered by the 1-second local timer """
        while True:
            delay = int(clamp(10, 1100, self._current_delay))
            await uasyncio.sleep_ms(delay) # this is a workaround for u=issues with the use of internal timer IRQ
            # measure the current period
            current_time = time.ticks_ms()
            current_period = clamp(10, 1100, current_time - self._last_time) # we keep only the value between 900 and 1100 ms
            self._last_time = current_time
            # compute error between current_period and 1000 ms target for PID corrector    
            self._current_delay = self.pid.filter(1000 - current_period)
            
            # update time
            if self.seconds==59:
                self.seconds = 0
                self._next_minute()
            else:
                self.seconds +=1
            self._display.update_date_and_time(self)
  

    



################### main ############################ 
# init main tasks
display = DCF_Display()
status_controller = StatusController(display)
local_clock_calendar = LocalTimeCalendar(display)
DCF_decoder = DCF_Decoder(TONE_GPIO, local_clock_calendar, status_controller)

# setup coroutines
DCF_frame_coroutine = DCF_decoder.frame_decoder()
DCF_signal_monitor_coroutine = DCF_decoder.DCF_signal_monitoring()
local_time_coroutine = local_clock_calendar.next_second()

#start coroutines
def excepHandler(loop, context):
    print(loop, context)
scheduler = uasyncio.get_event_loop()
scheduler.set_exception_handler(excepHandler)
scheduler.create_task(DCF_signal_monitor_coroutine)
scheduler.create_task(DCF_frame_coroutine)
scheduler.create_task(local_time_coroutine)
scheduler.run_forever()


