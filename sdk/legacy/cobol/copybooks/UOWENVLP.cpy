      ******************************************************************
      * UOWENVLP.cpy - CANONICAL UOW WIRE ENVELOPE RECORD
      *
      * Defines standard fixed-width 01-level record layout for 
      * mainframes, CICS COMMAREA, and batch file integration.
      ******************************************************************
       01  UOW-ENVELOPE-RECORD.
           05  UOW-PROTOCOL-VERSION         PIC X(08).
           05  UOW-OPERATION-ID             PIC X(64).
           05  UOW-OPERATION-VERSION         PIC X(08).
           05  UOW-REQUEST-ID               PIC X(36).
           05  UOW-CORRELATION-ID           PIC X(36).
           05  UOW-ACTOR.
               10  UOW-ACTOR-ID             PIC X(32).
               10  UOW-ACTOR-ROLE           PIC X(16).
               10  UOW-ACTOR-CLAIM-TYPE     PIC X(20).
           05  UOW-AUTHORITY-CONTEXT.
               10  UOW-AUTH-TOKEN           PIC X(64).
               10  UOW-AUTH-SIGNATURE       PIC X(64).
           05  UOW-CONSTRAINTS.
               10  UOW-TIMEOUT-MS           PIC 9(08) COMP-3.
               10  UOW-IDEMPOTENCY-KEY      PIC X(64).
               10  UOW-CAUSAL-EPOCH         PIC 9(08) COMP-3.
           05  UOW-EVIDENCE-CONTEXT.
               10  UOW-PARENT-EVIDENCE-HASH PIC X(64).
           05  UOW-REPLY-TO                 PIC X(64).
           05  UOW-PAYLOAD-LENGTH           PIC 9(04) COMP.
           05  UOW-PAYLOAD-DATA             PIC X(512).
