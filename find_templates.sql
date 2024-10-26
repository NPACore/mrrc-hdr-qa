with cnts as (
  select
     count(*) as n, Project, SequenceName, param_id,
     min(AcqDate) first, max(AcqDate) last
   from acq a
   join acq_param p
     on a.param_id = p.rowid
   group by Project, SequenceName, param_id
) 
 select *
  from cnts
  group by Project, SequenceName
  having n = max(n);
