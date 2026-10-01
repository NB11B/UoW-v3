       IDENTIFICATION DIVISION.
       PROGRAM-ID. BATCHDEMO.
      ******************************************************************
      * Example: COBOL Batch Transaction preparing canonical UoW card
      ******************************************************************
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-RECORD.
           05  WS-VER   PIC X(8)  VALUE "1.0.0   ".
           05  WS-OP    PIC X(64) VALUE "inventory.reserve".
           05  WS-REQ   PIC X(36) VALUE "REQ-100299-BATCH-COBOL".
       PROCEDURE DIVISION.
           DISPLAY "COBOL Batch UoW Transaction Ready: " WS-OP.
           DISPLAY "Request Identifier: " WS-REQ.
           STOP RUN.
