       IDENTIFICATION DIVISION.
       PROGRAM-ID. UOWDEMO.
       AUTHOR. UOW-ARCHITECTURE-TEAM.
      ******************************************************************
      * Demonstration COBOL Batch Program consuming a Unit-of-Work
      * (inventory.reserve) via canonical copybook records.
      ******************************************************************
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.

      * Include canonical UoW copybooks
       COPY UOWENVLP.
       COPY UOWRSLT.

       01  WS-SKU-PARAM                 PIC X(16) VALUE "WIDGET-99".
       01  WS-QTY-PARAM                 PIC 9(04) VALUE 0012.
       01  WS-ORDER-ID                  PIC X(16) VALUE "ORD-101".

       PROCEDURE DIVISION.
       0000-MAIN-LOGIC.
           DISPLAY "INITIALIZING CANONICAL UOW REQUEST..."

      * Populate envelope fields according to canonical wire spec
           MOVE "1.0.0"                 TO UOW-PROTOCOL-VERSION
           MOVE "inventory.reserve"     TO UOW-OPERATION-ID
           MOVE "1.0.0"                 TO UOW-OPERATION-VERSION
           MOVE "REQ-CBL-20260924-001"   TO UOW-REQUEST-ID
           MOVE "CORR-TX-998822"        TO UOW-CORRELATION-ID
           MOVE "MAINFRAME-BATCH-01"    TO UOW-ACTOR-ID
           MOVE "BATCH_OPERATOR"        TO UOW-ACTOR-ROLE
           MOVE "AUTHENTICATED"         TO UOW-ACTOR-CLAIM-TYPE
           MOVE "IDEM-BATCH-009911"     TO UOW-IDEMPOTENCY-KEY

      * Format payload
           STRING '{"sku":"' DELIMITED BY SIZE
                  WS-SKU-PARAM DELIMITED BY SPACE
                  '","quantity":' DELIMITED BY SIZE
                  WS-QTY-PARAM DELIMITED BY SIZE
                  ',"order_id":"' DELIMITED BY SIZE
                  WS-ORDER-ID DELIMITED BY SPACE
                  '"}' DELIMITED BY SIZE
                  INTO UOW-PAYLOAD-DATA
           END-STRING
           MOVE 64                      TO UOW-PAYLOAD-LENGTH

           DISPLAY "DISPATCHING ENVELOPE TO UOW BRIDGE FOR: " 
                   UOW-OPERATION-ID

      * Simulate invocation return into UOW-RESULT-RECORD
           MOVE UOW-REQUEST-ID          TO UOW-RES-REQUEST-ID
           MOVE "SUCCESS"               TO UOW-RES-STATUS
           MOVE "EVID-HASH-9988AABBCCDDEEFF00112233" 
                                        TO UOW-RES-EVIDENCE-HASH

           IF UOW-STATUS-SUCCESS
               DISPLAY "UOW COMPLETED SUCCESSFULLY!"
               DISPLAY "EVIDENCE RECEIPT: " UOW-RES-EVIDENCE-HASH
           ELSE
               DISPLAY "UOW FAILED: " UOW-RES-PRIMARY-ERROR-CODE
           END-IF

           GOBACK.
