"""
Arduino / Microcontrollers Quiz
Study tool with multiple choice, short answer, and open-ended questions.
Three difficulty levels, immediate feedback, and final score roast.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import random

# ============================================================
# QUESTION BANK
# ============================================================
# Types:
#   "mc"    -> multiple choice (one correct)
#   "short" -> short text answer, must match one of accepted strings (case-insensitive, stripped)
#   "open"  -> paragraph answer, self-graded against shown reference answer
# ============================================================

QUESTIONS = {
    "easy": [
        {
            "type": "open",
            "q": "What is a microcontroller and what is its main function?",
            "answer": "A microcontroller is a small integrated circuit (a 'computer on a chip') that contains a CPU, memory (RAM and flash), and programmable input/output peripherals. Its main function is to read inputs from sensors or switches, process that information according to a program, and control outputs such as motors, LEDs, or displays in embedded systems."
        },
        {
            "type": "open",
            "q": "Mention three key features of the Arduino UNO.",
            "answer": "1) Uses the ATmega328P microcontroller running at 16 MHz. 2) Has 14 digital I/O pins (6 of which support PWM) and 6 analog input pins. 3) Can be programmed via USB using the Arduino IDE thanks to its preloaded bootloader; it also operates at 5V logic."
        },
        {
            "type": "mc",
            "q": "What is the purpose of the bootloader in the Arduino UNO?",
            "options": [
                "Increase the microcontroller's speed",
                "Allow programming through the IDE over USB without an external programmer",
                "Control digital pins",
                "Generate PWM signals"
            ],
            "correct": 1
        },
        {
            "type": "open",
            "q": "Explain the difference between INPUT, OUTPUT, and INPUT_PULLUP in pin configuration.",
            "answer": "INPUT sets the pin to read external signals with a high-impedance state (the pin 'floats' if nothing is connected). OUTPUT sets the pin to drive a signal HIGH (5V) or LOW (0V) to control something. INPUT_PULLUP sets the pin as an input but also enables an internal resistor that pulls the pin HIGH by default, so it reads LOW only when the input is actively connected to ground (common for buttons)."
        },
        {
            "type": "short",
            "q": "Which Arduino function is used to read a button state from a digital pin?",
            "accepted": ["digitalread()", "digitalread"]
        },
        {
            "type": "short",
            "q": "What range of values does the analogRead() function return on the Arduino UNO?",
            "accepted": ["0-1023", "0 to 1023", "0,1023", "0 1023"]
        },
        {
            "type": "mc",
            "q": "What is PWM used for on the Arduino UNO?",
            "options": [
                "Reading analog sensors",
                "Simulating an analog output by rapidly switching a digital pin HIGH and LOW",
                "Communicating with Wi-Fi modules",
                "Storing long-term variables in EEPROM"
            ],
            "correct": 1
        },
        {
            "type": "short",
            "q": "List the PWM pins available on the Arduino UNO (comma separated, e.g., '3,5,6,9,10,11').",
            "accepted": ["3,5,6,9,10,11", "3, 5, 6, 9, 10, 11"]
        },
        {
            "type": "mc",
            "q": "What will the following line do?\n\n    analogWrite(9, 128);",
            "options": [
                "Set digital pin 9 HIGH",
                "Output a PWM signal on pin 9 at roughly 50% duty cycle",
                "Read an analog value from pin 9",
                "Send 128 bytes over Serial"
            ],
            "correct": 1
        },
        {
            "type": "open",
            "q": "What is the difference between Serial.print() and Serial.println()?",
            "answer": "Both send data over the serial port. Serial.print() writes the value without adding anything after it, so subsequent prints continue on the same line. Serial.println() does the same but appends a carriage return and newline ('\\r\\n'), moving the cursor to a new line in the Serial Monitor."
        },
        {
            "type": "mc",
            "q": "Which function is used to set a digital pin as output?",
            "options": [
                "digitalWrite(pin, OUTPUT)",
                "pinMode(pin, OUTPUT)",
                "setOutput(pin)",
                "analogWrite(pin, OUTPUT)"
            ],
            "correct": 1
        },
        {
            "type": "short",
            "q": "Which function introduces a pause of N milliseconds in Arduino? (just the function name with parentheses)",
            "accepted": ["delay()", "delay"]
        },
        {
            "type": "mc",
            "q": "What voltage does the Arduino UNO use for its logic HIGH level?",
            "options": ["3.3V", "5V", "12V", "1.8V"],
            "correct": 1
        },
        {
            "type": "short",
            "q": "Which two functions must every Arduino sketch contain? (answer in the form: setup(), loop())",
            "accepted": ["setup(),loop()", "setup(), loop()", "setup() loop()", "setup, loop", "setup,loop"]
        },
        {
            "type": "mc",
            "q": "Which pin on the Arduino UNO has a built-in LED attached?",
            "options": ["Pin 3", "Pin 7", "Pin 13", "Pin A0"],
            "correct": 2
        },
        {
            "type": "open",
            "q": "What is the difference between digital and analog signals, in the context of Arduino pins?",
            "answer": "A digital signal has only two states (HIGH / LOW, i.e. 5V or 0V on the UNO), used for things like buttons or LEDs. An analog signal is continuous and can take any value within a range; the Arduino reads analog signals on A0-A5 using a 10-bit ADC (values 0-1023) and can approximate analog output using PWM on specific digital pins."
        },
        {
            "type": "short",
            "q": "What is the default baud rate commonly used to start the Serial monitor in tutorials? (just the number)",
            "accepted": ["9600"]
        },
        {
            "type": "mc",
            "q": "Which of these components is typically used to limit current through an LED?",
            "options": ["Capacitor", "Resistor", "Diode", "Transistor"],
            "correct": 1
        },
        {
            "type": "mc",
            "q": "Which function reads an analog voltage on pin A0?",
            "options": [
                "digitalRead(A0)",
                "analogRead(A0)",
                "readAnalog(A0)",
                "Serial.read(A0)"
            ],
            "correct": 1
        },
        {
            "type": "short",
            "q": "How many analog input pins does the Arduino UNO have? (just the number)",
            "accepted": ["6"]
        },
        {
            "type": "short",
            "q": "How many digital I/O pins does the Arduino UNO have in total? (just the number)",
            "accepted": ["14"]
        },
        {
            "type": "mc",
            "q": "Which keyword is used to declare a constant value in Arduino C++?",
            "options": ["static", "const", "let", "final"],
            "correct": 1
        },
        {
            "type": "open",
            "q": "What is the purpose of the setup() function in Arduino?",
            "answer": "setup() runs exactly once when the board powers on or is reset. It is used to initialize things: configure pin modes with pinMode(), start serial communication with Serial.begin(), initialize sensors or libraries, and set initial variable states."
        },
        {
            "type": "open",
            "q": "What is the purpose of the loop() function in Arduino?",
            "answer": "loop() runs repeatedly forever after setup() finishes. It contains the main behavior of the program — reading sensors, making decisions, and driving outputs. Each iteration executes top to bottom, then immediately starts over."
        },
        {
            "type": "mc",
            "q": "Which port is typically used to upload a sketch to the Arduino UNO?",
            "options": ["HDMI", "USB", "Ethernet", "VGA"],
            "correct": 1
        },
        {
            "type": "short",
            "q": "Which function writes HIGH or LOW to a digital pin? (function name with parentheses)",
            "accepted": ["digitalwrite()", "digitalwrite"]
        },
        {
            "type": "mc",
            "q": "What does the IDE acronym stand for?",
            "options": [
                "Integrated Development Environment",
                "Internal Digital Electronics",
                "Internet Data Exchange",
                "Industrial Device Engine"
            ],
            "correct": 0
        },
        {
            "type": "open",
            "q": "Give an example of an input device and an output device you might connect to an Arduino.",
            "answer": "Input examples: push button, potentiometer, temperature sensor (LM35), ultrasonic distance sensor (HC-SR04), photoresistor. Output examples: LED, buzzer, DC motor (via driver), servo motor, LCD display."
        },
        {
            "type": "short",
            "q": "What symbol is used in C++/Arduino for a single-line comment? (one symbol or set of symbols)",
            "accepted": ["//"]
        },
        {
            "type": "mc",
            "q": "Which value represents a logic LOW on the Arduino UNO?",
            "options": ["5V", "3.3V", "0V", "-5V"],
            "correct": 2
        },
    ],

    "medium": [
        {
            "type": "open",
            "q": "Explain the purpose of the map() function in Arduino and write its basic syntax.",
            "answer": "map() re-scales a number from one range to another using integer math. It is typically used to convert an analogRead value (0-1023) into a useful range (e.g., 0-255 for PWM, or 0-180 for a servo angle).\n\nSyntax:\n    map(value, fromLow, fromHigh, toLow, toHigh);\n\nExample:\n    int pwm = map(analogRead(A0), 0, 1023, 0, 255);"
        },
        {
            "type": "open",
            "q": "What is a stepper motor and how does it differ from a regular DC motor?",
            "answer": "A stepper motor rotates in discrete, fixed angular increments ('steps') by energizing its coils in a specific sequence, giving precise open-loop position control without a feedback sensor. A regular DC motor spins continuously when voltage is applied; its speed depends on voltage and its position is not known — you must add an encoder and a control loop to position it. Steppers trade top speed and efficiency for precision; DC motors are simpler, faster, and cheaper but imprecise."
        },
        {
            "type": "open",
            "q": "Write an example command sent over the Serial Monitor (and the corresponding Arduino code snippet) to turn on an LED connected to pin 13.",
            "answer": "From the Serial Monitor the user could type the character '1' and press Send.\n\nOn the Arduino side:\n\n    void setup() {\n      pinMode(13, OUTPUT);\n      Serial.begin(9600);\n    }\n\n    void loop() {\n      if (Serial.available()) {\n        char c = Serial.read();\n        if (c == '1') digitalWrite(13, HIGH);\n        else if (c == '0') digitalWrite(13, LOW);\n      }\n    }"
        },
        {
            "type": "open",
            "q": "What is an interrupt in the context of microcontrollers and why are they useful?",
            "answer": "An interrupt is a hardware or software signal that causes the CPU to pause whatever it is currently doing, jump to a special function called an Interrupt Service Routine (ISR), run it, and then return to where it left off. They are useful because they let the microcontroller react immediately to events (like a button press, a timer overflow, or incoming serial data) without having to constantly poll for them in loop(), which saves CPU time and guarantees fast response."
        },
        {
            "type": "mc",
            "q": "What effect does this code have?\n\n    attachInterrupt(digitalPinToInterrupt(2), handleButtonPress, FALLING);",
            "options": [
                "Continuously polls pin 2 in the main loop",
                "Calls handleButtonPress() every time pin 2 transitions from HIGH to LOW",
                "Calls handleButtonPress() every time pin 2 transitions from LOW to HIGH",
                "Disables all interrupts on pin 2"
            ],
            "correct": 1
        },
        {
            "type": "open",
            "q": "Describe an example where using an interrupt is more efficient than using a conditional check inside loop().",
            "answer": "Example: an emergency stop button on a robot. If you checked the button inside loop() with digitalRead(), you could miss a very short press while the code is busy (e.g., during a delay(), a long serial print, or a blocking sensor read). With an interrupt attached to the button's pin on FALLING edge, the ISR fires the instant the button is pressed regardless of what the main program is doing, so the robot stops immediately. Other good cases: counting pulses from an encoder, waking from sleep on an event, timing the echo of an ultrasonic sensor."
        },
        {
            "type": "mc",
            "q": "On the Arduino UNO, which pins support external interrupts via attachInterrupt()?",
            "options": [
                "Pins 0 and 1",
                "Pins 2 and 3",
                "Pins 9 and 10",
                "Pins A0 and A1"
            ],
            "correct": 1
        },
        {
            "type": "open",
            "q": "Analyze the following code. What does it do?\n\n    void setup() {\n      pinMode(7, INPUT_PULLUP);\n      pinMode(13, OUTPUT);\n    }\n    void loop() {\n      if (digitalRead(7) == LOW) {\n        digitalWrite(13, HIGH);\n      } else {\n        digitalWrite(13, LOW);\n      }\n    }",
            "answer": "It configures pin 7 as an input with the internal pull-up resistor enabled, so it reads HIGH by default. Pin 13 is set as output. In the loop, if pin 7 reads LOW (the button connected between pin 7 and GND is pressed), the onboard LED on pin 13 turns ON; otherwise it stays OFF. In short: 'press a button -> light an LED', using INPUT_PULLUP so no external resistor is needed."
        },
        {
            "type": "short",
            "q": "Which function detaches a previously attached external interrupt on pin 2? (function name + its single argument, e.g. foo(x))",
            "accepted": [
                "detachinterrupt(digitalpintointerrupt(2))",
                "detachinterrupt(2)"
            ]
        },
        {
            "type": "open",
            "q": "What is the difference between a blocking delay (delay()) and a non-blocking delay using millis()? Which is better and why?",
            "answer": "delay() halts the entire program for the specified time — nothing else runs, interrupts aside. Using millis() you record the current time and compare it against a saved timestamp (e.g., if (millis() - last >= 1000) { ... }), which lets the rest of loop() keep running. The millis() approach is better for any real program because it allows multiple tasks to appear to run in parallel (blinking an LED, reading sensors, handling Serial) without freezing the system."
        },
        {
            "type": "mc",
            "q": "Analog output via analogWrite() produces a PWM signal. By default on the UNO, what is the approximate PWM frequency on most pins?",
            "options": ["~50 Hz", "~490 Hz", "~16 MHz", "~1 MHz"],
            "correct": 1
        },
        {
            "type": "open",
            "q": "What is debouncing and why is it necessary when reading a mechanical button?",
            "answer": "When a mechanical button is pressed or released, the contacts physically bounce for a few milliseconds, producing multiple fast HIGH/LOW transitions instead of one clean edge. Without debouncing, a single press can be counted as many presses. Debouncing filters these spurious transitions, either in hardware (RC filter / Schmitt trigger) or in software (ignore state changes that happen within, say, 20-50 ms of the last accepted change, commonly using millis())."
        },
        {
            "type": "open",
            "q": "Write a short sketch that reads a potentiometer on A0 and uses its value to control the brightness of an LED on pin 9.",
            "answer": "void setup() {\n  pinMode(9, OUTPUT);\n}\n\nvoid loop() {\n  int raw = analogRead(A0);               // 0 - 1023\n  int pwm = map(raw, 0, 1023, 0, 255);    // scale to PWM range\n  analogWrite(9, pwm);\n}"
        },
        {
            "type": "mc",
            "q": "Which variable type is recommended for a timestamp captured from millis()?",
            "options": ["int", "long", "unsigned long", "float"],
            "correct": 2
        },
        {
            "type": "open",
            "q": "Explain what Serial.available() returns and how it is typically used.",
            "answer": "Serial.available() returns the number of bytes currently waiting in the serial receive buffer. It is typically used as a gate before reading: if (Serial.available() > 0) { char c = Serial.read(); ... }. This avoids calling Serial.read() when there is nothing to read (which would return -1)."
        },
        {
            "type": "open",
            "q": "What does this code print to the Serial Monitor, and why?\n\n    int x = 5;\n    int y = 2;\n    Serial.println(x / y);",
            "answer": "It prints '2'. Both x and y are int, so the division is integer division — the fractional part is discarded. To get 2.5 you would need to make at least one operand a float, e.g. Serial.println((float)x / y);"
        },
        {
            "type": "short",
            "q": "Which qualifier must be used on a variable that is shared between an ISR and the main loop? (one keyword)",
            "accepted": ["volatile"]
        },
        {
            "type": "mc",
            "q": "What does Serial.begin(9600); do?",
            "options": [
                "Sends the number 9600 over serial",
                "Initializes serial communication at 9600 bits per second",
                "Waits 9600 milliseconds before starting",
                "Sets the baud rate for I2C"
            ],
            "correct": 1
        },
        {
            "type": "open",
            "q": "Describe what an H-bridge is and why it is used with DC motors.",
            "answer": "An H-bridge is a circuit made of four switching elements (typically transistors or MOSFETs) arranged in the shape of an 'H' around the motor. By turning on diagonal pairs of switches, it lets the microcontroller reverse the polarity of the voltage applied to a DC motor, so the motor can spin in either direction. It also isolates the motor's higher current/voltage from the microcontroller's logic pins. Common driver ICs: L298N, L293D, DRV8833."
        },
        {
            "type": "mc",
            "q": "Which library is commonly used to control servos on the Arduino UNO?",
            "options": ["Stepper.h", "Servo.h", "Wire.h", "SPI.h"],
            "correct": 1
        },
        {
            "type": "open",
            "q": "Write a sketch that toggles an LED on pin 8 every second using millis() (no delay()).",
            "answer": "const int LED = 8;\nunsigned long lastToggle = 0;\nbool state = false;\n\nvoid setup() {\n  pinMode(LED, OUTPUT);\n}\n\nvoid loop() {\n  if (millis() - lastToggle >= 1000) {\n    lastToggle = millis();\n    state = !state;\n    digitalWrite(LED, state);\n  }\n}"
        },
        {
            "type": "short",
            "q": "Which function returns the time in milliseconds since the board started? (function name + parentheses)",
            "accepted": ["millis()", "millis"]
        },
        {
            "type": "mc",
            "q": "What does the 'RISING' mode in attachInterrupt() trigger on?",
            "options": [
                "Only when the pin reads HIGH",
                "A transition from LOW to HIGH",
                "A transition from HIGH to LOW",
                "Any change in pin state"
            ],
            "correct": 1
        },
        {
            "type": "open",
            "q": "What does the following loop do?\n\n    for (int i = 0; i < 5; i++) {\n      digitalWrite(13, HIGH);\n      delay(200);\n      digitalWrite(13, LOW);\n      delay(200);\n    }",
            "answer": "It blinks the LED on pin 13 five times. Each blink is 200 ms ON followed by 200 ms OFF, so the full sequence takes about 2 seconds. Because it uses delay(), the microcontroller cannot do anything else during the blinking."
        },
        {
            "type": "open",
            "q": "Explain what a pull-down resistor does and when you would use one instead of a pull-up.",
            "answer": "A pull-down resistor (typically 10k ohms) connects an input pin to GND, so the pin reads LOW by default when nothing else is driving it. You would use a pull-down when your button/switch connects the input pin to +5V when pressed (so pressed = HIGH, released = LOW). Use a pull-up when the button connects the pin to GND when pressed (pressed = LOW). The Arduino UNO has built-in pull-ups but no built-in pull-downs, so pull-downs must be added externally."
        },
        {
            "type": "mc",
            "q": "Which of the following is NOT a valid pinMode() argument?",
            "options": ["INPUT", "OUTPUT", "INPUT_PULLUP", "OUTPUT_PULLUP"],
            "correct": 3
        },
        {
            "type": "open",
            "q": "What does the Arduino function constrain(x, a, b) do? Give one example.",
            "answer": "constrain(x, a, b) clamps x to the range [a, b]. If x < a it returns a; if x > b it returns b; otherwise it returns x. Useful right after map() to make sure a value doesn't exceed valid limits.\n\nExample:\n    int pwm = map(sensor, 0, 1023, 0, 255);\n    pwm = constrain(pwm, 0, 255);\n    analogWrite(9, pwm);"
        },
        {
            "type": "short",
            "q": "Which Arduino function returns the time in microseconds since startup? (name + parentheses)",
            "accepted": ["micros()", "micros"]
        },
        {
            "type": "mc",
            "q": "Why should ISRs (Interrupt Service Routines) be as short as possible?",
            "options": [
                "They consume flash memory faster the longer they are",
                "They block other interrupts and can cause the main loop to miss timing / delay() and millis() to drift",
                "The compiler refuses long ISRs",
                "They only work if they are under 10 lines"
            ],
            "correct": 1
        },
        {
            "type": "open",
            "q": "What is the difference between '==' and '=' in Arduino C++?",
            "answer": "'=' is the assignment operator: x = 5 stores 5 into x. '==' is the equality comparison: x == 5 evaluates to true if x equals 5, false otherwise. Writing 'if (x = 5)' by mistake is a classic bug — it assigns 5 to x (and evaluates to 5, which is truthy) instead of comparing."
        },
    ],

    "hard": [
        {
            "type": "open",
            "q": "Analyze the following sketch in detail. What does it do, and what potential issue does it have?\n\n    volatile bool pressed = false;\n    const int BTN = 2;\n    const int LED = 13;\n\n    void isr() {\n      pressed = true;\n    }\n\n    void setup() {\n      pinMode(BTN, INPUT_PULLUP);\n      pinMode(LED, OUTPUT);\n      attachInterrupt(digitalPinToInterrupt(BTN), isr, FALLING);\n    }\n\n    void loop() {\n      if (pressed) {\n        digitalWrite(LED, !digitalRead(LED));\n        pressed = false;\n      }\n    }",
            "answer": "It toggles the LED on pin 13 every time the button on pin 2 is pressed. The ISR sets a volatile flag, and the main loop reacts to it and resets the flag — a correct, standard interrupt pattern (ISRs stay short; work happens in loop()).\n\nPotential issue: no debouncing. Mechanical bounce on the button can fire the ISR multiple times per press, producing erratic toggling. Fix by checking millis() inside the ISR and ignoring edges within, say, 50 ms of the last accepted one, or by debouncing the hardware with an RC filter."
        },
        {
            "type": "open",
            "q": "Write a complete sketch that uses an external interrupt on pin 2 to count button presses (with software debouncing), and prints the count over Serial whenever it changes. Explain the key design choices.",
            "answer": "volatile unsigned long lastIsrMs = 0;\nvolatile unsigned long count     = 0;\nvolatile bool changed            = false;\nconst unsigned long DEBOUNCE_MS  = 50;\n\nvoid isr() {\n  unsigned long now = millis();\n  if (now - lastIsrMs >= DEBOUNCE_MS) {\n    lastIsrMs = now;\n    count++;\n    changed = true;\n  }\n}\n\nvoid setup() {\n  Serial.begin(9600);\n  pinMode(2, INPUT_PULLUP);\n  attachInterrupt(digitalPinToInterrupt(2), isr, FALLING);\n}\n\nvoid loop() {\n  if (changed) {\n    noInterrupts();\n    unsigned long c = count;\n    changed = false;\n    interrupts();\n    Serial.print(\"Count: \");\n    Serial.println(c);\n  }\n}\n\nKey choices:\n- 'volatile' on every variable shared with the ISR so the compiler reloads them from RAM.\n- Debouncing INSIDE the ISR with millis() keeps the main loop simple.\n- The main loop copies 'count' with interrupts briefly disabled to avoid reading a half-updated value (atomic access).\n- FALLING mode is used because INPUT_PULLUP makes the pressed state LOW."
        },
        {
            "type": "open",
            "q": "Explain what happens if you call Serial.print() or delay() inside an ISR, and why.",
            "answer": "Both are risky and generally forbidden.\n\n- delay() relies on millis(), which is updated by the Timer0 overflow interrupt. Since interrupts are disabled while another ISR runs, millis() does not advance, so delay() inside an ISR will either hang forever or, at best, behave incorrectly.\n- Serial.print() uses interrupt-driven TX on modern cores; if the TX buffer fills up it waits for the transmit-complete interrupt to fire, which can't happen because we're already inside an ISR. The result is a deadlock or lost characters.\n\nRule of thumb: ISRs must be short and non-blocking. Set a flag or push data into a small buffer, and let loop() do the heavy work (printing, delays, sensor reads)."
        },
        {
            "type": "open",
            "q": "Design a non-blocking state machine (in Arduino C++) that blinks an LED with a pattern: ON 200 ms, OFF 200 ms, ON 200 ms, OFF 1000 ms, and repeats forever. No delay() allowed.",
            "answer": "enum State { S1_ON, S1_OFF, S2_ON, LONG_OFF };\nState state = S1_ON;\nunsigned long tPrev = 0;\nconst int LED = 13;\n\nvoid setup() {\n  pinMode(LED, OUTPUT);\n}\n\nvoid loop() {\n  unsigned long now = millis();\n  switch (state) {\n    case S1_ON:\n      digitalWrite(LED, HIGH);\n      if (now - tPrev >= 200) { tPrev = now; state = S1_OFF; }\n      break;\n    case S1_OFF:\n      digitalWrite(LED, LOW);\n      if (now - tPrev >= 200) { tPrev = now; state = S2_ON; }\n      break;\n    case S2_ON:\n      digitalWrite(LED, HIGH);\n      if (now - tPrev >= 200) { tPrev = now; state = LONG_OFF; }\n      break;\n    case LONG_OFF:\n      digitalWrite(LED, LOW);\n      if (now - tPrev >= 1000) { tPrev = now; state = S1_ON; }\n      break;\n  }\n}\n\nThe LED-write calls could be moved to 'on-enter' transitions to avoid writing every iteration, but writing digitalWrite repeatedly is cheap and keeps the example clear."
        },
        {
            "type": "open",
            "q": "Why is it dangerous to read a multi-byte volatile variable (like an unsigned long counter updated in an ISR) directly from loop()? How do you fix it?",
            "answer": "On the AVR (8-bit CPU of the UNO), a 32-bit unsigned long is read/written one byte at a time. An interrupt can fire between two of those byte accesses, leaving you with a 'torn' value made of some old and some new bytes — potentially a wildly wrong number.\n\nFix: wrap the read in a critical section so the ISR cannot run mid-read:\n\n    noInterrupts();\n    unsigned long snapshot = count;\n    interrupts();\n\nOr use the ATOMIC_BLOCK macro from <util/atomic.h>:\n\n    uint32_t snapshot;\n    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { snapshot = count; }"
        },
        {
            "type": "mc",
            "q": "You attach an interrupt with mode CHANGE on pin 2 and press/release a noisy button once. Without debouncing, what is the MOST LIKELY behavior of your ISR counter?",
            "options": [
                "It increments exactly twice (one press + one release)",
                "It increments once",
                "It increments many times — several on the press edge, several on the release edge, due to contact bounce",
                "It does not increment at all because CHANGE is invalid on pin 2"
            ],
            "correct": 2
        },
        {
            "type": "open",
            "q": "Explain how PWM is used to dim an LED and why the LED appears smoothly dimmed rather than blinking. Mention the role of the human eye and of PWM frequency.",
            "answer": "analogWrite(pin, duty) generates a square wave at a fixed frequency (~490 Hz on most UNO pins, ~980 Hz on pins 5/6) with a duty cycle proportional to duty/255. The LED is actually switching fully ON and fully OFF, but the average current — and therefore the perceived brightness — is proportional to the duty cycle.\n\nThe eye acts as a low-pass filter: above roughly 60-100 Hz humans can no longer resolve individual flashes due to flicker fusion, so the fast switching at ~490 Hz is perceived as a steady, dimmer light. If the PWM frequency were too low (say, 20 Hz), you would see the LED flicker instead of appearing dim."
        },
        {
            "type": "open",
            "q": "The following code compiles but the LED does not blink correctly. Find and explain the bug, then give the corrected version.\n\n    int LED = 13;\n    int interval = 500;\n    long previous = 0;\n\n    void setup() { pinMode(LED, OUTPUT); }\n\n    void loop() {\n      if (millis() - previous > interval) {\n        previous = millis();\n        digitalWrite(LED, !digitalRead(LED));\n      }\n    }",
            "answer": "Bug: 'previous' is declared as a signed 'long'. millis() returns 'unsigned long'. After about 24.8 days, millis() wraps around, and because of the signed/unsigned mix the subtraction 'millis() - previous' can produce unexpected values when interpreted as signed long, causing the LED timing to glitch (and it can even go wrong earlier on edge cases). The canonical idiom requires unsigned arithmetic so that the wrap-around 'just works'.\n\nCorrected:\n\n    const int LED = 13;\n    const unsigned long interval = 500;\n    unsigned long previous = 0;\n\n    void setup() { pinMode(LED, OUTPUT); }\n\n    void loop() {\n      unsigned long now = millis();\n      if (now - previous >= interval) {\n        previous = now;\n        digitalWrite(LED, !digitalRead(LED));\n      }\n    }"
        },
        {
            "type": "mc",
            "q": "You want to measure a pulse width of ~40 microseconds coming from an ultrasonic sensor. Which approach is MOST appropriate on an Arduino UNO?",
            "options": [
                "Use digitalRead() inside loop() and count iterations",
                "Use delay() between reads",
                "Use pulseIn() or an input-capture / external interrupt with micros() timestamps",
                "Use analogRead() on the echo pin"
            ],
            "correct": 2
        },
        {
            "type": "open",
            "q": "Write a sketch that reads a potentiometer on A0 and, using an interrupt from a push-button on pin 2, stores the current reading into a variable each time the button is pressed. The main loop prints the stored value once per second using millis().",
            "answer": "volatile int  savedValue = 0;\nvolatile bool newSample  = false;\nvolatile unsigned long lastIsr = 0;\nconst unsigned long DEBOUNCE = 50;\n\nvoid captureISR() {\n  unsigned long now = millis();\n  if (now - lastIsr < DEBOUNCE) return;\n  lastIsr = now;\n  savedValue = analogRead(A0);  // OK on AVR for a single 10-bit read, but see note\n  newSample  = true;\n}\n\nunsigned long tPrint = 0;\n\nvoid setup() {\n  Serial.begin(9600);\n  pinMode(2, INPUT_PULLUP);\n  attachInterrupt(digitalPinToInterrupt(2), captureISR, FALLING);\n}\n\nvoid loop() {\n  if (millis() - tPrint >= 1000) {\n    tPrint = millis();\n    noInterrupts();\n    int v = savedValue;\n    bool fresh = newSample;\n    newSample = false;\n    interrupts();\n    Serial.print(\"Stored: \"); Serial.print(v);\n    Serial.println(fresh ? \" (new)\" : \"\");\n  }\n}\n\nNote: calling analogRead() inside the ISR is acceptable here because it is short and the main loop doesn't race with it, but in bigger projects you'd typically just set a flag and do the analogRead in loop() to keep the ISR minimal."
        },
        {
            "type": "open",
            "q": "Explain the memory layout of the Arduino UNO (ATmega328P): how much flash, SRAM, and EEPROM it has, and what each is used for.",
            "answer": "ATmega328P memory:\n- Flash: 32 KB (0.5 KB used by the bootloader, ~31.5 KB available). Non-volatile. Stores the compiled program. Written only when uploading a sketch.\n- SRAM: 2 KB. Volatile (lost on power-off). Holds global/static variables, the stack, and the heap — i.e. everything that changes at runtime.\n- EEPROM: 1 KB. Non-volatile, byte-addressable. For small settings/calibration values that must survive power cycles. Limited write endurance (~100 000 cycles per cell), so don't write to it on every loop iteration."
        },
        {
            "type": "open",
            "q": "Describe what PROGMEM does and when you would use it. Give a short code example.",
            "answer": "PROGMEM is an AVR keyword that places a constant in flash memory instead of SRAM. The UNO only has 2 KB of SRAM but 32 KB of flash, so large constant data — lookup tables, long strings, images, fonts — should live in flash to avoid exhausting RAM. Accessing PROGMEM data requires special functions like pgm_read_byte() or the F() macro for strings.\n\nExample:\n\n    const char msg[] PROGMEM = \"A long constant string stored in flash\";\n\n    void setup() {\n      Serial.begin(9600);\n      for (unsigned i = 0; i < strlen_P(msg); i++) {\n        char c = pgm_read_byte(&msg[i]);\n        Serial.print(c);\n      }\n      // Or more simply for literals:\n      Serial.println(F(\" also in flash\"));\n    }"
        },
        {
            "type": "mc",
            "q": "Which statement about the AVR's interrupt system is TRUE?",
            "options": [
                "Interrupts can nest by default on the AVR",
                "Global interrupts are automatically disabled upon entering an ISR and re-enabled on exit",
                "ISRs run with higher CPU clock speed than loop()",
                "attachInterrupt() can be called on any digital pin of the UNO"
            ],
            "correct": 1
        },
        {
            "type": "open",
            "q": "Compare polling vs. interrupts for handling a quadrature encoder on a fast-moving motor. Which is appropriate and why?",
            "answer": "A quadrature encoder produces two square waves (A and B) whose relative phase encodes direction and whose edges encode position. On a fast motor, edges can arrive every few tens of microseconds.\n\n- Polling in loop() can easily miss edges if the loop is not fast enough or is busy with other work (Serial prints, sensor reads). You lose counts, so position drifts.\n- Interrupts on the A (and ideally B) channel fire on every edge and update a volatile counter in a tiny ISR. No counts are missed as long as the ISR is shorter than the edge interval.\n\nFor anything beyond very slow encoders, interrupts (or dedicated hardware like the ATmega's Input Capture / external counters) are the right choice. On the UNO, pins 2 and 3 are the two available external interrupts, which matches a single quadrature encoder nicely."
        },
        {
            "type": "open",
            "q": "Predict the Serial Monitor output of this sketch and explain each line:\n\n    void setup() {\n      Serial.begin(9600);\n      int a = 7;\n      int b = 4;\n      Serial.println(a / b);\n      Serial.println(a % b);\n      Serial.println((float)a / b);\n      Serial.println(a > b && b > 0);\n    }\n    void loop() {}",
            "answer": "Output (each on its own line):\n\n    1\n    3\n    1.75\n    1\n\n- a / b with both int: 7 / 4 = 1 (integer division truncates).\n- a % b: 7 modulo 4 = 3.\n- (float)a / b: promotes a to float, so the division is floating-point: 1.75. Serial.println prints floats with 2 decimal places by default, giving '1.75'.\n- (a > b && b > 0): 7 > 4 is true (1), 4 > 0 is true (1), logical AND is true, printed as '1'. Booleans in Arduino print as 0 or 1."
        },
        {
            "type": "open",
            "q": "Explain what the following does and what must be added to make it thread-safe with an ISR:\n\n    unsigned long ticks = 0;\n    void loop() {\n      ticks++;\n      if (ticks % 1000 == 0) Serial.println(ticks);\n    }",
            "answer": "It simply increments a counter in the main loop and prints it every 1000 iterations. As written it does NOT involve an ISR so there is no race.\n\nTo make it safe once an ISR also writes to 'ticks':\n1. Declare 'ticks' as 'volatile unsigned long' so the compiler reloads it from RAM.\n2. Because it's a 32-bit value on an 8-bit CPU, any read from loop() must be atomic:\n\n       noInterrupts();\n       unsigned long t = ticks;\n       interrupts();\n       if (t % 1000 == 0) Serial.println(t);\n\n   Or use ATOMIC_BLOCK from <util/atomic.h>.\n3. Any increment done in loop() of a variable that the ISR also writes should be wrapped similarly, otherwise the ISR can fire between the read and the write-back of 'ticks++'."
        },
        {
            "type": "short",
            "q": "On the ATmega328P, which hardware timer drives millis() and delay() by default? (answer: timer0, timer1, or timer2)",
            "accepted": ["timer0", "timer 0", "0"]
        },
        {
            "type": "mc",
            "q": "Which scenario would BEST justify using EEPROM instead of SRAM or flash?",
            "options": [
                "Storing a real-time counter updated thousands of times per second",
                "Storing the compiled program itself",
                "Storing user calibration settings that must survive power-off and rarely change",
                "Storing a temporary loop variable"
            ],
            "correct": 2
        },
        {
            "type": "open",
            "q": "Write a concise example showing how to safely share a 16-bit counter between a Timer1 compare-match ISR (firing at 1 kHz) and loop(), where loop() needs to compute a moving average every 100 ms.",
            "answer": "#include <TimerOne.h>   // library that wraps Timer1\n\nvolatile uint16_t sample = 0;\nvolatile bool     fresh  = false;\n\nvoid onTick() {\n  // Suppose we read a sensor fast here\n  sample = analogRead(A0);\n  fresh  = true;\n}\n\nunsigned long tAvg = 0;\nuint32_t acc = 0;\nuint16_t n   = 0;\n\nvoid setup() {\n  Serial.begin(9600);\n  Timer1.initialize(1000);          // 1000 us = 1 kHz\n  Timer1.attachInterrupt(onTick);\n}\n\nvoid loop() {\n  if (fresh) {\n    noInterrupts();\n    uint16_t s = sample;\n    fresh = false;\n    interrupts();\n    acc += s;\n    n++;\n  }\n  if (millis() - tAvg >= 100) {\n    tAvg = millis();\n    if (n) {\n      Serial.println(acc / n);\n      acc = 0;\n      n = 0;\n    }\n  }\n}\n\nKey points: 'sample' and 'fresh' are volatile; the 16-bit read is protected by a tiny critical section; the heavy work (printing, averaging) is in loop(), keeping the ISR fast."
        },
        {
            "type": "open",
            "q": "What is I2C, what wires does it need, and what is its main advantage over using N separate GPIOs for N sensors?",
            "answer": "I2C (Inter-Integrated Circuit) is a synchronous, half-duplex, multi-drop serial bus. It uses just two wires plus ground: SDA (data) and SCL (clock), both open-drain and pulled up with resistors. Each device on the bus has a unique 7-bit (or 10-bit) address.\n\nAdvantage: you can connect dozens of peripherals (sensors, displays, EEPROMs, RTCs…) using the same two pins on the microcontroller, instead of wiring a dedicated bus per device. The master addresses each device by its address; arbitration and clock stretching handle multiple devices gracefully. On the UNO, I2C is on pins A4 (SDA) and A5 (SCL), handled by the Wire library."
        },
        {
            "type": "mc",
            "q": "You have a 5V ultrasonic sensor (HC-SR04) and want to interface its 5V echo line with a 3.3V microcontroller. What is the correct approach?",
            "options": [
                "Connect directly; the 3.3V MCU is tolerant by default",
                "Use a level shifter or a resistor divider on the echo line to drop 5V to ~3.3V",
                "Power the sensor at 3.3V to be safe",
                "Put a capacitor in series with the echo line"
            ],
            "correct": 1
        },
        {
            "type": "open",
            "q": "Explain why floating-point math is slow on the Arduino UNO and what you can do about it when speed matters.",
            "answer": "The ATmega328P is an 8-bit CPU with no hardware floating-point unit. Every float operation is emulated in software by the compiler's runtime, which takes many more cycles than integer math (a single float multiply can take dozens to hundreds of cycles versus ~2 for an 8-bit integer multiply).\n\nWhen speed matters you can:\n- Keep values in integer units (e.g., millivolts, milli-degrees, micrometers) and scale at the end.\n- Use fixed-point arithmetic (e.g., represent 1.75 as 175 with an implicit /100 scale).\n- Pre-compute constant expressions at compile time.\n- Avoid div/modulo by powers of two (use shifts for integers).\n- Use look-up tables stored in PROGMEM instead of computing functions like sin() on the fly.\n- If truly required, move the computation to a more capable MCU (e.g., a 32-bit ARM with an FPU)."
        },
        {
            "type": "open",
            "q": "Give two common reasons an Arduino sketch may fail to upload with an 'avrdude: stk500_getsync() attempt... not in sync' error, and how to fix each.",
            "answer": "1) Wrong serial port selected in the IDE. The sketch is being sent to a port that isn't the Arduino. Fix: Tools -> Port, select the correct COM/tty device (often named ttyACM0, ttyUSB0, or COMx).\n\n2) The board/chip selection doesn't match (e.g., 'Arduino Nano' selected while connected to a UNO, or the wrong bootloader variant for a Nano clone with the 'Old Bootloader'). Fix: Tools -> Board, and for Nano clones try 'Processor: ATmega328P (Old Bootloader)'.\n\nOther common causes worth mentioning: the serial port is held open by another program (Serial Monitor of another IDE); the USB cable is charge-only; something on pins 0/1 (RX/TX) is interfering with upload — disconnect it; the bootloader is corrupted and must be reburned with an ISP programmer."
        },
        {
            "type": "open",
            "q": "What is the purpose of the Watchdog Timer (WDT) and how would you use it as a last-resort safety net in an Arduino sketch?",
            "answer": "The Watchdog Timer is a separate hardware timer that, once enabled, must be periodically reset ('kicked' or 'fed') by the program. If the main program hangs (infinite loop, deadlock, corruption) and fails to kick it within the configured timeout, the WDT forces a hardware reset, recovering the system automatically.\n\nUsage sketch:\n\n    #include <avr/wdt.h>\n\n    void setup() {\n      // ... your initialization ...\n      wdt_enable(WDTO_2S);   // reset board if loop() hangs >2 s\n    }\n\n    void loop() {\n      doWork();\n      wdt_reset();           // kick the dog every iteration\n    }\n\nKey rules: enable AFTER boot-time work that may be slow; disable it explicitly with wdt_disable() if you need to do something that legitimately takes longer than the timeout; on the UNO's old bootloaders, a WDT reset may loop — using the optiboot bootloader (default on modern UNOs) fixes that."
        },
        {
            "type": "open",
            "q": "Describe, step by step, what happens from the instant you press a button wired to pin 2 (with INPUT_PULLUP and a FALLING external interrupt attached) until your ISR finishes running.",
            "answer": "1. Before the press, pin 2 is held HIGH by the internal pull-up.\n2. You press the button, connecting pin 2 to GND. The voltage on the pin falls from ~5V to ~0V, producing a FALLING edge.\n3. The AVR's external interrupt hardware (INT0 for pin 2) detects the edge and sets the INTF0 flag in the EIFR register.\n4. Since the global interrupt enable bit (I in SREG) is set and INT0 is unmasked (EIMSK bit 0 = 1), the CPU finishes the current instruction and prepares to service the interrupt.\n5. The CPU pushes the current program counter onto the stack, clears the global interrupt enable (I = 0, so nested interrupts are disabled by default), and jumps to the INT0 vector in the interrupt vector table.\n6. The vector contains a jump to the generated Arduino dispatcher, which in turn calls your registered ISR (the function you passed to attachInterrupt).\n7. Your ISR runs. It should be short: typically set a volatile flag, maybe read a pin, update a counter, etc.\n8. When your ISR returns, the dispatcher returns, and the RETI instruction pops the saved PC and re-enables global interrupts (I = 1).\n9. Execution resumes in loop() exactly where it was interrupted, as if nothing had happened — except that your flag/counter has been updated.\n\nIf the button bounces, steps 2-8 may repeat several times in a few milliseconds unless you debounce."
        },
        {
            "type": "mc",
            "q": "You want the most accurate periodic sampling (e.g., every exactly 1.000 ms) on an Arduino UNO. What is the BEST approach?",
            "options": [
                "Call delay(1) in loop()",
                "Call delayMicroseconds(1000) in loop()",
                "Configure a hardware timer (Timer1/Timer2) in CTC mode with a compare-match interrupt at 1 kHz",
                "Use analogRead() in a tight loop"
            ],
            "correct": 2
        },
        {
            "type": "open",
            "q": "What does 'noInterrupts()' do, and what are the risks of leaving interrupts disabled for too long?",
            "answer": "noInterrupts() clears the global interrupt enable flag (I in SREG), preventing any ISR from firing until interrupts() is called to re-enable them. It's used to create short critical sections that access shared data atomically, or around timing-sensitive bit-banged protocols.\n\nRisks of leaving them off too long:\n- millis() and micros() will not advance correctly because they rely on the Timer0 overflow interrupt, so delay() and timing code drift or freeze.\n- Serial TX/RX, which is interrupt-driven, can lose bytes or stall.\n- External events (button edges, encoder pulses, sensor ready signals) are missed entirely.\n- PWM on some pins relies on timer interrupts for frequency changes (though analogWrite itself is hardware-generated on AVR, so basic PWM keeps running).\n\nRule of thumb: keep the noInterrupts()/interrupts() window as short as physically possible — ideally just a handful of instructions."
        },
        {
            "type": "open",
            "q": "Compare HIGH-side and LOW-side switching of a load (e.g., an LED or small motor) with a MOSFET driven by a microcontroller pin. Which is more common for Arduino-level projects and why?",
            "answer": "In LOW-side switching, an N-channel MOSFET sits between the load and GND: the load is always connected to +V, and the MCU drives the MOSFET's gate to ground or to V_gs above threshold to turn the load on/off. It's simple — the source is at GND so the MCU's 5V gate drive is enough to fully enhance the MOSFET — and is by far the most common choice in Arduino projects.\n\nIn HIGH-side switching, the switch sits between +V and the load: for an N-channel MOSFET you need a gate voltage higher than V+, which requires a charge-pump or a gate driver. It's simpler with a P-channel MOSFET, but P-channel parts with low R_ds(on) are pricier and you still usually need a small NPN/level-shifter because the MCU's logic level may not be enough to fully turn a P-FET off when V+ > 5V.\n\nLow-side is preferred unless the load MUST have a fixed ground (common ground with other systems, H-bridges, etc.), in which case high-side switching (or a purpose-built driver IC) becomes necessary."
        },
        {
            "type": "open",
            "q": "You are designing a robot that reads three IR line sensors, drives two motors via PWM, and must respond instantly to an emergency-stop button. Explain, at a high level, how you would structure the Arduino code (setup, loop, interrupts, timing).",
            "answer": "- setup():\n  * Serial.begin() for debugging.\n  * pinMode() for all inputs (sensors, E-stop with INPUT_PULLUP) and outputs (motor PWM, DIR pins, LEDs).\n  * attachInterrupt(digitalPinToInterrupt(ESTOP_PIN), onEstop, FALLING) so the button is handled instantly.\n  * Initialize motor driver and library objects, zero all state variables.\n\n- Shared state:\n  * volatile bool estopFlag = false; written by the ISR, read in loop().\n\n- ISR (onEstop):\n  * Keep it tiny. Set estopFlag = true; maybe also hard-cut PWM by writing 0 directly to the OCRx registers or calling analogWrite(pin, 0) (safe because it doesn't block).\n\n- loop():\n  1) If estopFlag, immediately set motor PWM to 0, park into an 'ESTOPPED' state, blink an LED, and optionally require a reset command to leave that state.\n  2) Otherwise, use a millis()-based scheduler to run subtasks at their own rates:\n       - every 5 ms: read IR sensors, update a line-position estimate.\n       - every 10 ms: run the PID/PD controller that outputs motor PWM values.\n       - every 100 ms: send telemetry over Serial.\n  3) Never use delay() inside loop(); all timing uses millis() so all subtasks coexist.\n\n- Extra notes:\n  * Put motor outputs behind a single writeMotors(left, right) function so the ESTOP path can zero both in one place.\n  * Use constrain()/map() when converting sensor or controller outputs to PWM.\n  * Consider a Watchdog Timer as a final safety net."
        },
    ],
}


FINAL_MESSAGES = {
    "bodrio": [
        "bodrio fr fr, go open the book 💀",
        "dumbahh answers, keep studying brah",
        "this ain't it chief, review the basics and come back",
        "bro really thought this was a multiple choice of vibes",
        "keep studying brah, the microcontroller is not your enemy (yet)",
    ],
    "mid": [
        "mid performance, you're halfway to cracked",
        "not bad not great, lock in one more study session",
        "you got the vibes down, now learn the details",
        "decent run, but the robot still fears you a little",
        "respectable, but the bootloader has seen better defenders",
    ],
    "good": [
        "aight aight, you ready for this shi 🔥",
        "you cooking, keep that same energy in the lab",
        "solid, LARC Open 2026 better watch out",
        "certified Arduino enjoyer behavior",
        "you lowkey cracked at this",
    ],
    "einstein": [
        "einstein type shi 🧠⚡",
        "touch grass, you've clearly been studying too hard (respect)",
        "Anthropic is hiring btw",
        "bro is the human datasheet",
        "you ARE the microcontroller at this point",
    ],
}


# ============================================================
# GUI
# ============================================================

BG        = "#1e1e2e"
FG        = "#cdd6f4"
ACCENT    = "#89b4fa"
OK_GREEN  = "#a6e3a1"
BAD_RED   = "#f38ba8"
SUBTLE    = "#313244"
MUTED     = "#6c7086"


class QuizApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Arduino / Microcontrollers Quiz")
        self.root.geometry("900x700")
        self.root.configure(bg=BG)

        self.difficulty = None
        self.questions  = []
        self.idx        = 0
        self.score      = 0
        self.answered   = False  # lock state after submitting

        self._build_start_screen()

    # ---------- helpers ----------
    def _clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _title(self, parent, text, size=18):
        lbl = tk.Label(parent, text=text, bg=BG, fg=ACCENT,
                       font=("Segoe UI", size, "bold"))
        lbl.pack(pady=(20, 10))
        return lbl

    def _btn(self, parent, text, cmd, bg=ACCENT, fg=BG):
        b = tk.Button(parent, text=text, command=cmd,
                      bg=bg, fg=fg, activebackground=SUBTLE,
                      activeforeground=FG, relief="flat",
                      font=("Segoe UI", 12, "bold"),
                      padx=16, pady=8, cursor="hand2")
        return b

    # ---------- start screen ----------
    def _build_start_screen(self):
        self._clear()
        self._title(self.root, "ARDUINO QUIZ", 28)
        tk.Label(self.root,
                 text="microcontrollers, PWM, interrupts & more",
                 bg=BG, fg=MUTED, font=("Segoe UI", 11, "italic")
                 ).pack(pady=(0, 30))

        tk.Label(self.root, text="Choose your difficulty:",
                 bg=BG, fg=FG, font=("Segoe UI", 14)).pack(pady=(10, 20))

        frame = tk.Frame(self.root, bg=BG)
        frame.pack(pady=10)

        tk.Label(self.root,
                 text="How many questions this round?",
                 bg=BG, fg=FG, font=("Segoe UI", 12)).pack(pady=(30, 5))
        self.count_var = tk.IntVar(value=10)
        counter = tk.Spinbox(self.root, from_=5, to=30,
                             textvariable=self.count_var, width=5,
                             font=("Segoe UI", 14),
                             bg=SUBTLE, fg=FG, buttonbackground=SUBTLE,
                             relief="flat")
        counter.pack()

        for (label, key, color) in [
            ("Easy",   "easy",   "#a6e3a1"),
            ("Medium", "medium", "#f9e2af"),
            ("Hard",   "hard",   "#f38ba8"),
        ]:
            b = self._btn(frame, label,
                          lambda k=key: self._start_quiz(k),
                          bg=color, fg=BG)
            b.pack(side="left", padx=14)

        tk.Label(self.root,
                 text=f"({len(QUESTIONS['easy'])} easy • "
                      f"{len(QUESTIONS['medium'])} medium • "
                      f"{len(QUESTIONS['hard'])} hard available)",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)
                 ).pack(side="bottom", pady=20)

    # ---------- start a run ----------
    def _start_quiz(self, difficulty):
        self.difficulty = difficulty
        bank = list(QUESTIONS[difficulty])
        random.shuffle(bank)
        n = min(self.count_var.get(), len(bank))
        self.questions = bank[:n]
        self.idx       = 0
        self.score     = 0
        self._show_question()

    # ---------- render one question ----------
    def _show_question(self):
        self._clear()
        q = self.questions[self.idx]
        self.answered = False

        # Top bar: progress + score
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=20, pady=10)
        tk.Label(top,
                 text=f"Question {self.idx + 1} / {len(self.questions)}   "
                      f"[{self.difficulty.upper()}]",
                 bg=BG, fg=MUTED, font=("Segoe UI", 11)
                 ).pack(side="left")
        tk.Label(top, text=f"Score: {self.score}",
                 bg=BG, fg=ACCENT, font=("Segoe UI", 11, "bold")
                 ).pack(side="right")

        # Question text
        qframe = tk.Frame(self.root, bg=BG)
        qframe.pack(fill="x", padx=20, pady=(10, 10))
        qtext = tk.Text(qframe, height=self._guess_height(q["q"]),
                        bg=SUBTLE, fg=FG, font=("Consolas", 12),
                        wrap="word", relief="flat", padx=12, pady=10,
                        borderwidth=0)
        qtext.insert("1.0", q["q"])
        qtext.config(state="disabled")
        qtext.pack(fill="x")

        # Answer area based on type
        self.answer_frame = tk.Frame(self.root, bg=BG)
        self.answer_frame.pack(fill="both", expand=True, padx=20, pady=10)

        if q["type"] == "mc":
            self._render_mc(q)
        elif q["type"] == "short":
            self._render_short(q)
        else:
            self._render_open(q)

        # Buttons
        btns = tk.Frame(self.root, bg=BG)
        btns.pack(fill="x", padx=20, pady=10)
        self.submit_btn = self._btn(btns, "Submit", self._submit)
        self.submit_btn.pack(side="left")
        self.next_btn = self._btn(btns, "Next →", self._next,
                                  bg=SUBTLE, fg=FG)
        self.next_btn.pack(side="right")
        self.next_btn.config(state="disabled")

        # Feedback area
        self.feedback = tk.Label(self.root, text="", bg=BG,
                                 fg=FG, font=("Segoe UI", 11, "italic"),
                                 wraplength=820, justify="left")
        self.feedback.pack(fill="x", padx=20, pady=(0, 10))

    def _guess_height(self, text):
        lines = text.count("\n") + 1 + len(text) // 80
        return max(2, min(lines + 1, 14))

    # ---------- multiple choice ----------
    def _render_mc(self, q):
        self.mc_var = tk.IntVar(value=-1)
        self.mc_buttons = []
        for i, opt in enumerate(q["options"]):
            rb = tk.Radiobutton(
                self.answer_frame, text=opt,
                variable=self.mc_var, value=i,
                bg=BG, fg=FG,
                selectcolor=SUBTLE, activebackground=BG,
                activeforeground=ACCENT,
                font=("Segoe UI", 12), anchor="w",
                wraplength=800, justify="left",
                padx=8, pady=6,
            )
            rb.pack(fill="x", anchor="w", pady=2)
            self.mc_buttons.append(rb)

    # ---------- short answer ----------
    def _render_short(self, q):
        tk.Label(self.answer_frame, text="Type your answer:",
                 bg=BG, fg=MUTED, font=("Segoe UI", 11)
                 ).pack(anchor="w")
        self.short_entry = tk.Entry(
            self.answer_frame, bg=SUBTLE, fg=FG,
            insertbackground=FG, font=("Consolas", 13),
            relief="flat",
        )
        self.short_entry.pack(fill="x", ipady=6, pady=(4, 8))
        self.short_entry.focus_set()

    # ---------- open / paragraph ----------
    def _render_open(self, q):
        tk.Label(self.answer_frame,
                 text="Write your answer (self-graded — be honest):",
                 bg=BG, fg=MUTED, font=("Segoe UI", 11)
                 ).pack(anchor="w")
        self.open_text = scrolledtext.ScrolledText(
            self.answer_frame, bg=SUBTLE, fg=FG,
            insertbackground=FG, font=("Consolas", 11),
            wrap="word", relief="flat", height=10,
        )
        self.open_text.pack(fill="both", expand=True, pady=(4, 8))
        self.open_text.focus_set()

    # ---------- submit ----------
    def _submit(self):
        if self.answered:
            return
        q = self.questions[self.idx]
        self.answered = True
        self.submit_btn.config(state="disabled")
        self.next_btn.config(state="normal")

        if q["type"] == "mc":
            self._grade_mc(q)
        elif q["type"] == "short":
            self._grade_short(q)
        else:
            self._grade_open(q)

    def _grade_mc(self, q):
        chosen = self.mc_var.get()
        correct = q["correct"]
        # lock and color the radiobuttons
        for i, rb in enumerate(self.mc_buttons):
            rb.config(state="disabled")
            if i == correct:
                rb.config(fg=OK_GREEN, disabledforeground=OK_GREEN,
                          font=("Segoe UI", 12, "bold"))
            elif i == chosen and chosen != correct:
                rb.config(fg=BAD_RED, disabledforeground=BAD_RED,
                          font=("Segoe UI", 12, "bold"))
        if chosen == correct:
            self.score += 1
            self.feedback.config(
                text="✓ Correct!", fg=OK_GREEN)
        elif chosen == -1:
            self.feedback.config(
                text="No answer selected. "
                     f"Correct answer: {q['options'][correct]}",
                fg=BAD_RED)
        else:
            self.feedback.config(
                text=f"✗ Incorrect. Correct answer: "
                     f"{q['options'][correct]}",
                fg=BAD_RED)

    def _grade_short(self, q):
        raw = self.short_entry.get().strip().lower().replace(" ", "")
        accepted = [a.lower().replace(" ", "") for a in q["accepted"]]
        self.short_entry.config(state="disabled")
        if raw in accepted:
            self.score += 1
            self.short_entry.config(
                disabledbackground=SUBTLE,
                disabledforeground=OK_GREEN,
                readonlybackground=SUBTLE,
            )
            self.feedback.config(
                text=f"✓ Correct!  (Accepted: {q['accepted'][0]})",
                fg=OK_GREEN)
        else:
            self.short_entry.config(
                disabledbackground=SUBTLE,
                disabledforeground=BAD_RED,
                readonlybackground=SUBTLE,
            )
            self.feedback.config(
                text=f"✗ Incorrect. Correct answer: {q['accepted'][0]}",
                fg=BAD_RED)

    def _grade_open(self, q):
        # Self-grading: show reference answer, ask user whether their
        # answer was essentially correct.
        user_ans = self.open_text.get("1.0", "end").strip()
        self.open_text.config(state="disabled")

        # Show the reference answer in a fresh frame under the answer
        ref_frame = tk.Frame(self.root, bg=BG)
        ref_frame.pack(fill="both", expand=False, padx=20, pady=5)
        tk.Label(ref_frame, text="Reference answer:",
                 bg=BG, fg=OK_GREEN,
                 font=("Segoe UI", 11, "bold")
                 ).pack(anchor="w")
        ref_box = scrolledtext.ScrolledText(
            ref_frame, bg=SUBTLE, fg=OK_GREEN,
            font=("Consolas", 11), wrap="word",
            relief="flat", height=8,
        )
        ref_box.insert("1.0", q["answer"])
        ref_box.config(state="disabled")
        ref_box.pack(fill="x", pady=(4, 6))

        if not user_ans:
            self.feedback.config(
                text="No answer written — counted as incorrect.",
                fg=BAD_RED)
            return

        # ask the user to self-grade
        grade_frame = tk.Frame(self.root, bg=BG)
        grade_frame.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(grade_frame,
                 text="Did your answer cover the main points?",
                 bg=BG, fg=FG, font=("Segoe UI", 11)
                 ).pack(side="left", padx=(0, 10))

        def mark(correct):
            for w in grade_frame.winfo_children():
                w.destroy()
            if correct:
                self.score += 1
                self.feedback.config(
                    text="✓ Counted as correct.", fg=OK_GREEN)
            else:
                self.feedback.config(
                    text="✗ Counted as incorrect — review the reference.",
                    fg=BAD_RED)

        self._btn(grade_frame, "Yes, I got it",
                  lambda: mark(True),
                  bg=OK_GREEN, fg=BG).pack(side="left", padx=4)
        self._btn(grade_frame, "No, I missed it",
                  lambda: mark(False),
                  bg=BAD_RED, fg=BG).pack(side="left", padx=4)

    # ---------- next / end ----------
    def _next(self):
        self.idx += 1
        if self.idx >= len(self.questions):
            self._show_final()
        else:
            self._show_question()

    def _show_final(self):
        self._clear()
        n = len(self.questions)
        pct = self.score / n if n else 0

        self._title(self.root, "FINAL SCORE", 26)

        tk.Label(self.root,
                 text=f"{self.score} / {n}   ({pct*100:.0f}%)",
                 bg=BG, fg=ACCENT, font=("Segoe UI", 36, "bold")
                 ).pack(pady=20)

        if pct < 0.4:
            bucket = "bodrio"
            color  = BAD_RED
        elif pct < 0.7:
            bucket = "mid"
            color  = "#f9e2af"
        elif pct < 0.9:
            bucket = "good"
            color  = OK_GREEN
        else:
            bucket = "einstein"
            color  = "#cba6f7"

        msg = random.choice(FINAL_MESSAGES[bucket])
        tk.Label(self.root, text=msg, bg=BG, fg=color,
                 font=("Segoe UI", 18, "bold"),
                 wraplength=800, justify="center"
                 ).pack(pady=20)

        tk.Label(self.root,
                 text=f"Difficulty: {self.difficulty.upper()}",
                 bg=BG, fg=MUTED, font=("Segoe UI", 12)
                 ).pack(pady=10)

        btns = tk.Frame(self.root, bg=BG)
        btns.pack(pady=30)
        self._btn(btns, "Play Again",
                  self._build_start_screen).pack(side="left", padx=10)
        self._btn(btns, "Quit", self.root.destroy,
                  bg=SUBTLE, fg=FG).pack(side="left", padx=10)


def main():
    root = tk.Tk()
    QuizApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()