unit UoWTypes;

interface

uses
  SysUtils;

type
  TUoWStatus = (
    uowStatusSuccess,
    uowStatusRejected,
    uowStatusError,
    uowStatusPending
  );

  PUoWEnvelope = ^TUoWEnvelope;
  TUoWEnvelope = record
    ProtocolVersion: ShortString;
    Operation: ShortString;
    OperationVersion: ShortString;
    RequestId: ShortString;
    CorrelationId: ShortString;
    ActorId: ShortString;
    ClaimType: ShortString;
    PayloadJson: AnsiString;
  end;

  PUoWResult = ^TUoWResult;
  TUoWResult = record
    RequestId: ShortString;
    Operation: ShortString;
    Status: TUoWStatus;
    EvidenceHash: ShortString;
    DurationMs: Double;
    ResultJson: AnsiString;
    ErrorMessage: ShortString;
  end;

function UoWValidateEnvelope(EnvelopeJson: PAnsiChar): Integer; cdecl; external 'uow_core.dll';
function UoWExecute(EnvelopeJson: PAnsiChar; var ResultJsonOut: PAnsiChar): Integer; cdecl; external 'uow_core.dll';
procedure UoWFreeString(Ptr: PAnsiChar); cdecl; external 'uow_core.dll';

implementation

end.
