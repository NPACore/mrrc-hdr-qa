#!/usr/bin/env Rscript
# add copy of AR's sheet to database for alerting
# 20260309WF - init

# load packages, installing if needed
# alternatively:
#   guix shell r r-dbplyr r-readxl r-rsqlite r-dplyr r-pacman -- Rscript ./01b_xsl2db.R
'pacman' %in% installed.packages() || {install.packages('pacman');TRUE}
pacman::p_load(dbplyr, dplyr, readxl, RSQLite)

# read studes from AR provided sheet
d <- read_excel('studies.xlsx') |>
    # remove spaces from columns
    rename(PI=`PI Last Name`,
           Project=`MRRC Project Code`,
           Title=`Study Title`,
           email=`PI Email`,
           cc=`CC Email`)

# confirm we have all rows we want, subset to just those
cols <- c("PI","Project","Title","Hrs","Physicist", "email", "cc")
stopifnot(all(cols %in% names(d)))
d <- d |> select(all_of(cols))

# hard code addresses, but obscure a bit so we dont leak emails into the world
addr <- c(Moon="chm", Schirda="s", Kim="t")
pitt <- function(n) {
    a<-addr[n]
    if(is.na(a)) return(NA)
    paste0(a,'@pitt.edu')
}
to_emails <- \(x) strsplit(x, ',') |>
                      unlist() |> lapply(pitt) |> paste0(collapse=",")

# cleanup physicist. set emails
d <- d |>
    mutate(contact = Physicist |>
               # Victor not on any current study
               gsub(patt='(Victor|Yushmanov)[,/]?',repl='') |>
               # Old Chan can be ignored
               gsub(patt='Moon.2019./',repl='') |>
               # remove parentheticals
               gsub(patt='\\(.*\\)|set up',repl='') |>
               # consistent separator. comma for email later
               gsub(patt='/',repl=',') |>
               gsub(patt=' ',repl=''),
           phys_mail = Vectorize(to_emails)(contact) |> unname(),
           Project=toupper(Project))

#  scp npac@mrrc-cerebro2:src/mrrc-hdr-qa/db.sqlite ./
con <- DBI::dbConnect(RSQLite::SQLite(), dbname = "db.sqlite")
# DBI::dbListTables(con)
# [1] "acq"  "acq_param" "template_by_count"
p_existing <-
   tbl(con,sql("select * from acq join acq_param on acq.param_id = acq_param.rowid" )) |>
    group_by(Project) |>
    summarise(n=n(),
              ndays=count(distinct(AcqDate)),
              first=min(AcqDate),
              last=max(AcqDate)) |>
    collect() |>
    mutate(Project=gsub('.*[\\^ ]','',Project),
           pu=toupper(Project))

projects <- merge(p_existing, d, by.x='pu',by.y="Project", all.x=T)

# check on missing
projects |>
    filter(ndays>5,is.na(phys_mail)) |>
    select(ndays, PI, Project, first, last) |>
    arrange(last)

# what to add to DB
projects_update <- projects |>
    filter(!is.na(PI)|!is.na(phys_mail)) |>
    select(all_of(cols))

# TODO: don't overwrite without adding any removed from xls but still in the db
#       pull from db, antijoin on project, rbind
# tbl(con,"project") |> collect() |> anti_join(projects_update, by="Project") |> rbind(projects_update)

# create table
copy_to(con, projects_update, name="project", overwrite=T, temporary=F)
DBI::dbDisconnect(con)
