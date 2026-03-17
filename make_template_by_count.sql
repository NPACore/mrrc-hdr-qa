drop table if exists template_by_count;

create table template_by_count as
with cnts as (
  select
     count(*) as n, Project, SequenceName, param_id,
     min(AcqDate) first, max(AcqDate) last
   from acq a
   join acq_param p
     on a.param_id = p.rowid
   group by Project, SequenceName, param_id
),
best as (
  select *
  from cnts
  group by Project, SequenceName
  having n = max(n)
)
select b.*,
  (
    SELECT GROUP_CONCAT(te_val)
    FROM (
        SELECT DISTINCT CAST(p.TE AS REAL) as te_sort, p.TE as te_val
        FROM acq a
        JOIN acq_param p ON a.param_id = p.rowid
        WHERE p.Project = b.Project
        AND p.SequenceName = b.SequenceName
        ORDER BY te_sort
    )
  ) as multiecho_tes
from best b
order by Project, n desc;
