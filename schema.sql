-- acquisition. time id
create table acq (
  param_id integer, -- join to session-consitent settings
  AcqTime text,
  AcqDate text,
  SeiresNumber text,
  SubID text,
  Operator text
);

-- acq params that should match across sessions
create table acq_param (
  is_ideal timestamp,
  Project text,
  SequenceName text,
  -- TODO: should this be json blob? to extend easier?
  iPAT text,
  Comments text,
  SequenceType text,
  PED_major text,
  TR text,
  TE text,
  Matrix text,
  PixelResol text,
  BWP text,
  BWPPE text,
  FA text,
  TA text,
  FoV text
  -- TODO: add shim settings from CSA
);
