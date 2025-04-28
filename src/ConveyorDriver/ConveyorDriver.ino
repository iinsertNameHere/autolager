#include <Stepper.h>

#define DEVICE_ID "conv1"

const int stepsPerRevolution = 2048;  // Steps for one full rotation
const float gearRatio = 2.67; // Gear ratio of the Belt Drive
const int stepsPerShaftRevolution = (int)(gearRatio * stepsPerRevolution); // Steps for one full rotation of the Belt Shaft

Stepper stepper(stepsPerRevolution, 2, 4, 3, 5);
bool wasIdCheck = false;

void setup() {
  Serial.begin(9600);
  stepper.setSpeed(17);
}

void move(int direction, long targetSteps) {
  const int stepLimit = 32000; // Maximum safe step size per call
  long remainingSteps = abs(targetSteps);
  int stepDirection = (targetSteps > 0) ? direction : -direction;

  while (remainingSteps > 0) {
    int stepChunk = (remainingSteps > stepLimit) ? stepLimit : remainingSteps;
    stepper.step(stepDirection * stepChunk);
    remainingSteps -= stepChunk;
  }
}

void processCommand(String command) {
  command.trim(); // Remove spaces

  if (command == "ID") {
    Serial.println(DEVICE_ID);
    wasIdCheck = true;
  }
  else if (command.startsWith("MOVE ")) {
    command = command.substring(5); // Remove "MOVE "
    int direction = 1;
    
    if (command.startsWith("R")) {
      direction = -1;
      command = command.substring(1); // Remove "R"
    }
    
    float rotations = command.toFloat();
    long steps = rotations * stepsPerShaftRevolution;
    move(direction, steps);
  } 
  else if (command == "CALIB") {
    processCommand("MOVE 0.02");
    processCommand("MOVE R 0.02");
    processCommand("MOVE 0.02");
    processCommand("MOVE R 0.02");
    processCommand("MOVE 0.02");
    processCommand("MOVE R 0.02");
    processCommand("MOVE 0.7");
    processCommand("MOVE R 0.5");
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
      delay(100); // Shorter delay between commands
      ptr = strtok(NULL, ",");
    }
    if (!wasIdCheck) Serial.println("#NEXT#");
    else wasIdCheck = false;
  }
}
