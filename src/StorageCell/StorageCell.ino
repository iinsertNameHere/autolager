#include <Stepper.h>

#define DEVICE_ID "wall1"

const int stepsPerRevolution = 2048;  // Steps for one full rotation
Stepper stepper(stepsPerRevolution, 2, 4, 3, 5);

long currentStep = 0;  // Track position
bool directionFlipped = true; // Direction toggle
int motorSpeed = 15;   // Default speed (RPM)
bool wasIdCheck = false;

void setup() {
  Serial.begin(9600);
  stepper.setSpeed(motorSpeed);
}

void moveToPosition(int percentage) {
  if (percentage < 0) percentage = 0;
  if (percentage > 100) percentage = 100;

  long targetStep = map(percentage, 0, 100, 0, stepsPerRevolution + 5); // Convert % to steps
  long stepDifference = targetStep - currentStep;  // Calculate movement

  stepper.step(directionFlipped ? -stepDifference : stepDifference); // Apply direction
  currentStep = targetStep; // Update position
}

void processCommand(String command) {
  command.trim(); // Remove spaces

  if (command == "ID") {
    Serial.println(DEVICE_ID);
    wasIdCheck = true;
  } 
  else if (command.startsWith("POS ")) {
    int percentage = command.substring(4).toInt();
    if (percentage >= 0 && percentage <= 100) {
      moveToPosition(percentage);
    } else {
      Serial.println("Invalid POS value.");
    }
  } 
  else if (command == "HOME") {
    currentStep = 0;
  } 
  else if (command.startsWith("DIR ")) {
    String dir = command.substring(4); // Extract direction
    if (dir == "L") {
      directionFlipped = false;  // Set direction to forward
    } else if (dir == "R") {
      directionFlipped = true;  // Set direction to reverse
    } else {
      Serial.println("Invalid direction.");
    }
  }
  else if (command == "CALIB") {
    processCommand("UNLOAD");
    processCommand("LOAD");
  }
  else if (command == "LOAD") {
    stepper.setSpeed(18);
    processCommand("HOME");
    processCommand("DIR R");
    moveToPosition(42);
    processCommand("HOME");
    stepper.setSpeed(motorSpeed);
  }
  else if (command == "UNLOAD") {
    stepper.setSpeed(18);
    processCommand("HOME");
    processCommand("DIR L");
    moveToPosition(100);
    processCommand("HOME");
    moveToPosition(42);
    processCommand("HOME");
    stepper.setSpeed(motorSpeed);
  }
  else if (command.startsWith("SPEED ")) {
    int speed = command.substring(6).toInt();
    if (speed < 0) speed = 1;
    if (speed > 18) speed = 18;

    motorSpeed = speed;
    stepper.setSpeed(motorSpeed);
    
    Serial.print(motorSpeed);
  }
  else {
    Serial.print("Unknown command: ");
    Serial.println(command);
  }
}

void loop() {
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n'); // Read input
    input.trim();

    char *ptr = strtok(const_cast<char *>(input.c_str()), ","); // Split by comma
    while (ptr != NULL) {
      processCommand(String(ptr));
      delay(200); // Delay between commands
      ptr = strtok(NULL, ",");
    }
    if (!wasIdCheck) Serial.println("#NEXT#");
    else wasIdCheck = false;
  }
}
