# DCF77
 A project that decodes radio signal from DCF77 station.

The project uses lib_pico and debug_utility from [xiansnn/RP2-micropython](https://github.com/xiansnn/RP2-micropython). It uses also various GUI. In its last version I've used microGUI from [here](https://github.com/peterhinch/micropython-micro-gui)

For practical reason, the radio signal is received via a [WebSDR](http://www.websdr.org/) and in particular the one from [University of Twente in Enshede The Netherland](http://websdr.ewi.utwente.nl:8901/).

This is not the best way to decode DCF77, using a true radio receiver should be a better option. But this is a side project, derived from the [morse decoder project](https://github.com/xiansnn/Morse-decoder.git), for which, I wanted to experiment audio capture.

As a result, there is no direct reception of the radio signal: The radio signal is converted in audio signal by the WebSDR, then the audio signal is captured by a microphone (HW-484 or KY-038) and processed by a special circuitry to get a logical 3.3V level synchronized with the radio signal.

The figure below shows (in blue) the audio signal and (in yellow) the result of the electronic circuitry.
- 100ms pulse means a logic "0" bit
- 200ms pulse means a logic "1" bit
- absence of bit pulse means "start of a new minute"

![DS1Z_QuickPrint3](https://user-images.githubusercontent.com/42316927/210848424-deed29cc-a519-40ac-b566-91c250a3a806.png)

Several user interface have been used :
- a simple TextUI, a textual interface relying on frames, or text box, that I've derived from the original driers from MakerFabs from [here](https://github.com/xiansnn/RP2-micropython-libraries))
- the nanoGUI from [here](https://github.com/peterhinch/micropython-nano-gui)
- and finally the microGUI from [here](https://github.com/peterhinch/micropython-micro-gui)

TextUI and nanoGUI will probably no longer maintained. Only the microGUI will remain.
