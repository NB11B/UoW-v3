      ******************************************************************
      * UOWRSLT.cpy - CANONICAL UOW RESULT RECORD
      *
      * Defines standard fixed-width 01-level record layout for 
      * receiving execution outcomes, evidence hashes, and error status.
      ******************************************************************
       01  UOW-RESULT-RECORD.
           05  UOW-RES-REQUEST-ID           PIC X(36).
           05  UOW-RES-CORRELATION-ID       PIC X(36).
           05  UOW-RES-OPERATION-ID         PIC X(64).
           05  UOW-RES-STATUS               PIC X(12).
               88  UOW-STATUS-SUCCESS       VALUE 'SUCCESS'.
               88  UOW-STATUS-REJECTED      VALUE 'REJECTED'.
               88  UOW-STATUS-ERROR         VALUE 'ERROR'.
               88  UOW-STATUS-PENDING       VALUE 'PENDING'.
           05  UOW-RES-EVIDENCE.
               10  UOW-RES-EVIDENCE-HASH    PIC X(64).
               10  UOW-RES-PREV-REC-HASH    PIC X(64).
               10  UOW-RES-CERT-HASH        PIC X(64).
               10  UOW-RES-LEDGER-INDEX     PIC 9(08) COMP-3.
           05  UOW-RES-METADATA.
               10  UOW-RES-DURATION-MS      PIC 9(06) COMP-3.
               10  UOW-RES-HOST-NODE        PIC X(32).
           05  UOW-RES-ERROR-COUNT          PIC 9(02) COMP.
           05  UOW-RES-PRIMARY-ERROR-CODE   PIC X(32).
           05  UOW-RES-PRIMARY-ERROR-MSG    PIC X(80).
           05  UOW-RES-OUTPUT-LENGTH        PIC 9(04) COMP.
           05  UOW-RES-OUTPUT-DATA          PIC X(512).
