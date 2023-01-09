import uasyncio, ustruct, time
from machine import Timer
from lib_pico.async_push_button import Button
from lib_pico.ST7735_GUI import *

from debug_utility.pulses import Probe
probe_gpio = 16
probe = Probe(probe_gpio)

import micropython
TONE_GPIO = const(7) # the GPIO where DCF signal is received by MCU
WAIT_EOF = const("synchro in progress")
INIT = const("INIT")
OUT_OF_SYNC = const("out of synchro")
WAIT_SOF = const("waiting synchro")
LOST_SIG = const("DCF signal lost")
PRESENT_SIG = const("DCF signal present")
SYNC = const("synchronised")
FRAME_ERROR = const("frame error")
FRAME_INCOMPLETE = const("frame incomplete")

micropython.alloc_emergency_exception_buf(100)

class DCF_Display():
    """
Defines how the DCF decoder displays time, calendar and status on the ST7735 LCD module
"""
    def __init__(self):
        self.display = TFT_display()
        self.title_frame = self.display.add_frame("title",0,0,0,20,TFT.YELLOW)
        self.title_frame.write_text("DCF77 TIME")
        self.time_status_frame = self.display.add_frame("time_status",2,0,2,20,TFT.WHITE)
        self.signal_frame = self.display.add_frame("signal",1,0,1,20,TFT.WHITE)
        self.date_frame = self.display.add_frame("date",4,0,4,20,TFT.WHITE)
        self.second_frame = self.display.add_frame("second",13,0,13,20,TFT.WHITE)
        self.time_frame = self.display.add_frame("time",7,0,12,20,TFT.WHITE)
        
    def update_time_status(self, status, color):
        self.time_status_frame.foreground_color = color
        self.time_status_frame.write_text(f"{status:>20s}")
    
    def update_signal_status(self, status, color):
        self.signal_frame.foreground_color = color
        self.signal_frame.write_text(f"{status:>20s}")

    def update_date_and_time(self, time):
        self.date_frame.write_text(f"  {time.week_day:>3s} {time.day:0>2d} {time.month:3s} 20{time.year:0>2d}   ")
        self.second_frame.write_text(f"{time.seconds:0>2d} sec     zone:{time.time_zone:>4s}")
        self.time_frame.write_text(f"{time.hours:0>2d}:{time.minutes:0>2d}")




class StatusController():
    """
Manages local time, DCF decoder status as a simplified statemachine:
- update_xxxx are the methods that display time calendar and DCF signal status
- other methods are the events that trig state transitions
"""
    def __init__(self, display):
        self.display = display
        self.time_status = WAIT_SOF
        self.display.update_time_status(self.time_status, TFT.RED)
        self.signal_status = INIT
        self.display.update_signal_status(self.signal_status, TFT.RED)
#         print(INIT)
        
    def update_time_status(self, new_status, color):
        self.time_status = new_status
        self.display.update_time_status(self.time_status, color)
    
    def update_signal_status(self, new_status, color):
        self.signal_status = new_status
        self.display.update_signal_status(self.signal_status, color)
    
    def out_of_sync(self):
#         print(OUT_OF_SYNC)
        self.update_time_status(OUT_OF_SYNC, TFT.ORANGE)
        
    def signal_lost(self):
#         print(LOST_SIG)
        self.update_signal_status(LOST_SIG, TFT.RED)
        self.out_of_sync()
   
    def signal_present(self):
#         print (PRESENT_SIG)
        self.update_signal_status(PRESENT_SIG, TFT.GREEN)
        if self.time_status == OUT_OF_SYNC:
            self.update_time_status(WAIT_SOF, TFT.ORANGE)
        
    def EoF_received(self):
#         print("End of Frame received")
        if self.time_status==WAIT_SOF :
            self.update_time_status(WAIT_EOF, TFT.YELLOW)
        elif self.time_status == WAIT_SOF or self.time_status == OUT_OF_SYNC :
            self.update_time_status(WAIT_EOF,TFT.YELLOW)               

    def frame_error(self):
#         print(FRAME_ERROR)
        self.update_time_status(FRAME_ERROR, TFT.ORANGE)
        
    def frame_incomplete(self):
        if self.time_status != WAIT_EOF :
#         print(FRAME_INCOMPLETE)
            self.update_time_status(FRAME_INCOMPLETE, TFT.ORANGE)
    
    def sync_done(self):
#         print(SYNC)
        self.update_time_status(SYNC, TFT.GREEN)


class LocalTimeCalendar():
    """
The local clock/calendar, triggered by 1-second local timer
"""
    def __init__(self, display):
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
        self._last_time = 0
        self._current_delay = 1000

    
    def update_time(self, time_pack):
        """
When a DCF frame is received, the decoder packs a set of bites and this set is used to update the local clock
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
        """
method used when a "next minute" signal is received
"""
        self.seconds = 0
        
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
        """
coroutine triggered by the 1-second local timer
"""
        while True:
            current_time = time.ticks_ms()
            current_period = max(900,min(current_time - self._last_time,1100)) # we keep only the value between 900 and 1100 ms
            self._last_time = current_time
            delta = 1000 - current_period # we compute the error on the true current period
            self._current_delay = self._current_delay + int(delta/5)
            await uasyncio.sleep_ms(self._current_delay) # this will avoid to use internal timer IRQ
            probe.pulse_single() # for debugging purpose
            if self.seconds==59:
                self.seconds = 0
                self._next_minute()
            else:
                self.seconds +=1
            self._display.update_date_and_time(self)          




class DCF_Decoder():
    """
the DCF decoder algorithm, triggered by the DCF radio signal after being processed by electronic circuitry
"""
    def __init__(self, key_in_gpio, time, status_controller):
        self._DCF_clock_received = uasyncio.ThreadSafeFlag()
        Button("tone", key_in_gpio, pull=-1,
               interrupt_service_routine=self._DCF_clock_IRQ_handler,
               debounce_delay=80,
               active_HI=True, both_edge=True )
        self._time = time
        self._status_controller = status_controller
        self._current_string = ""
        self._frame = "" 
        self._DCF_signal_duration =0
        self._DCF_signal_is_high = True
        self._DCF_clock_received = uasyncio.ThreadSafeFlag()
        self._BCD_weight = [1, 2, 4, 8, 10, 20, 40, 80]
   
    def _push(self, data):
        self._current_string += data
#         probe.pulse_single(100)
#         print(f"[{len(self._current_string)-1:2d}]={data:1s}\t{self._current_string}")
        if data == "#" :
            self._frame = self._current_string
            self._current_string = "" 
            
    def _frame_completed(self):
#         print(f"frame length:{len(self._frame)}")
        return len(self._frame)==60
    
    def _DCF_clock_IRQ_handler(self, button):
        irq_state = machine.disable_irq()
        self._DCF_signal_duration = button.last_event_duration
        self._DCF_signal_is_high = button.is_pressed
        self._DCF_clock_received.set()
        machine.enable_irq(irq_state)     
        
    def _BCD_decoder(self, string):
        """
portions of frame encode date and time as BCD digits.
DCF frame is represented as a string of 0, 1 sequence.
"""
        value = 0
        for k in range(len(string)):
            value += self._BCD_weight[k]*int(string[k])
        return value
    
    def _frame_is_valid(self):
        s0 = (self._frame[0]  == "0") # check start of frame, always "0"
        s1 = (self._frame[20] == "1") # check start of time encoding, always "1"
        p1 = (self._frame[21:29].count("1")%2 == 0) # check parity
        p2 = (self._frame[29:36].count("1")%2 == 0) # check parity
        p3 = (self._frame[36:59].count("1")%2 == 0) # check parity
#         print(f"s0:{s0}\ts1:{s1}\tp1:{p1}\tp2:{p2}\tp3:{p3}")
        return (s0 and s1 and p1 and p2 and p3)
    
    async def time_decoder(self):
        """
coroutine that decode DCF signal, triggered by rising edge of received signal
"""
        while True:
            try:
                # the measured time [milliseconds] is the low level duration before the next rising edge
                # we have to anticipate a timeout in case of missing next rising edge
                await uasyncio.wait_for_ms(self._DCF_clock_received.wait(), 2000)
                self._DCF_clock_received.clear()
                self._status_controller.signal_present()
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
                        if self._DCF_signal_duration < 1850 : self._push("1")
                        else : self._push("0")
                        self._push("#") # we record a "next minute" signal (coded by "#")
                        self._time.start_new_minute()
                        self._status_controller.EoF_received()
                        if not self._frame_completed():   
                            self._status_controller.frame_incomplete()
                        else:
                            if not self._frame_is_valid():
                                self._status_controller.frame_error()
                            else: # we have now, a full frame without reception error
                                self._status_controller.sync_done()
                                time_zone_num = self._BCD_decoder(self._frame[17:19])
                                minutes = self._BCD_decoder(self._frame[21:28])
                                hours = self._BCD_decoder(self._frame[29:35])
                                day = self._BCD_decoder(self._frame[36:42])
                                week_day_num = self._BCD_decoder(self._frame[42:45])
                                month_num = self._BCD_decoder(self._frame[45:50])
                                year = self._BCD_decoder(self._frame[50:58])
                                self._time.update_time(ustruct.pack("6HB",
                                     year, month_num, day, week_day_num, hours, minutes, time_zone_num))
            except uasyncio.TimeoutError:
                self._status_controller.signal_lost()

    



################### main ############################ 
# init main tasks
display = DCF_Display()
status_controller = StatusController(display)
local_clock_calendar = LocalTimeCalendar(display)
DCF_decoder = DCF_Decoder(TONE_GPIO, local_clock_calendar, status_controller)

# setup coroutines
DCF_time_coroutine = DCF_decoder.time_decoder()
local_time_coroutine = local_clock_calendar.next_second()

#start coroutines
scheduler = uasyncio.get_event_loop()
scheduler.create_task(DCF_time_coroutine)
scheduler.create_task(local_time_coroutine)
scheduler.run_forever()


