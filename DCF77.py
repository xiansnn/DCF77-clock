import uasyncio, ustruct
from machine import Timer
from lib_pico.async_push_button import Button
from lib_pico.ST7735_GUI import *

from pulse_utility.pulses import Probe
probe_gpio = 16
probe = Probe(probe_gpio)

import micropython
TONE_GPIO = const(7)
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
    def __init__(self):
        self.display = TFT_display()
        self.title_frame = self.display.add_frame("title",0,0,0,20,TFT.WHITE)
        self.title_frame.write_text("DCF77 TIME")
        self.time_status_frame = self.display.add_frame("time_status",2,0,2,20,TFT.WHITE)
        self.signal_frame = self.display.add_frame("signal",1,0,1,20,TFT.WHITE)
        self.date_frame = self.display.add_frame("date",4,0,4,20,TFT.YELLOW)
        self.time_frame = self.display.add_frame("time",6,0,6,20,TFT.YELLOW)
        
    def update_time_status(self, status, color):
        self.time_status_frame.foreground_color = color
        self.time_status_frame.write_text(f"{status:>20s}")
    
    def update_signal_status(self, status, color):
        self.signal_frame.foreground_color = color
        self.signal_frame.write_text(f"{status:>20s}")

    def update_date_and_time(self, time):
        self.date_frame.write_text(f"  {time.week_day:>3s} {time.day:0>2d} {time.month:3s} 20{time.year:0>2d}   ")
        self.time_frame.write_text(f"{time.hours:0>2d}:{time.minutes:0>2d}:{time.seconds:0>2d}{time.time_zone:>4s}")




class StatusController():
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
#         print("EoF_received")
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
    def __init__(self, display):
        self._display = display
        Timer().init(mode=Timer.PERIODIC, period=1000, callback=self._local_clock_IRQ_handler)
        self._local_clock_elapsed = uasyncio.ThreadSafeFlag()
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

    def _local_clock_IRQ_handler(self, time):
        irq_state = machine.disable_irq()
        self._local_clock_elapsed.set()
        machine.enable_irq(irq_state)
    
    def update_time(self, time_pack):
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
        while True:
            await self._local_clock_elapsed.wait()
            self._local_clock_elapsed.clear()
            probe.pulse_single()
            if self.seconds==59:
                self.seconds = 0
                self._next_minute()
            else:
                self.seconds +=1
            self._display.update_date_and_time(self)          




class DCF_Decoder():
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
        probe.pulse_single(100)
        self._current_string += data
        if data == "#" :
            self._frame = self._current_string
            self._current_string = ""
        
            
    def _frame_completed(self):
        return len(self._frame)==59
    
    def _DCF_clock_IRQ_handler(self, button):
        irq_state = machine.disable_irq()
        self._DCF_signal_duration = button.last_event_duration
        self._DCF_signal_is_high = button.is_pressed
        self._DCF_clock_received.set()
        machine.enable_irq(irq_state)     
        
    def _BCD_decoder(self, string):
        value = 0
        for k in range(len(string)):
            value += self._BCD_weight[k]*int(string[k])
        return value
    
    def _frame_is_valid(self):
        p1=self._frame[21:29].count("1")%2 == 0
        p2=self._frame[29:36].count("1")%2 == 0
        p3=self._frame[36:59].count("1")%2 == 0
        return (p1 and p2 and p3)
    
    async def time_decoder(self):       
        while True:
            try: 
                await uasyncio.wait_for_ms(self._DCF_clock_received.wait(), 2000)
                self._DCF_clock_received.clear()
                self._status_controller.signal_present()
                if self._DCF_signal_is_high :# the measured time [milliseconds] is the one of the previous signal period
                    if self._DCF_signal_duration >= 750 and self._DCF_signal_duration < 850 :
                        self._push("1")
                    elif self._DCF_signal_duration >= 850 and self._DCF_signal_duration < 950 :
                        self._push("0")
                    elif self._DCF_signal_duration >= 1750 and self._DCF_signal_duration < 1950 :
                        self._push("#")
                        self._time.start_new_minute()
                        self._status_controller.EoF_received()
                        if not self._frame_completed():
                            self._status_controller.frame_incomplete()
                        else:
                            if not self._frame_is_valid():
                                self._status_controller.frame_error()
                            else:
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
time = LocalTimeCalendar(display)
DCF_decoder = DCF_Decoder(TONE_GPIO, time, status_controller)

# setup coroutines
DCF_time_coroutine = DCF_decoder.time_decoder()
local_time_coroutine = time.next_second()

#start coroutines
scheduler = uasyncio.get_event_loop()
scheduler.create_task(DCF_time_coroutine)
scheduler.create_task(local_time_coroutine)
scheduler.run_forever()


