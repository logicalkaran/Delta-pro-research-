# Strategy V2 — Regime × Session × Execution

Status: RESEARCH_ONLY
Raw events: {N}
Feature samples: {len(E)}
Candidate configurations: 2925

## Top candidates
- FLOW_MOM_0.3_3.0_S | maker pen=0 | 300s 8/16 | train n=23 avg=18.100 PF=12.567091058634423 | val n=5 avg=1.668 PF=1.7261414081652666 | test n=11 avg=-2.486 PF=0.4516868562431064
- FLOW_MOM_0.3_3.0_S | maker pen=0 | 300s 10/20 | train n=23 avg=17.892 PF=12.948199889022519 | val n=5 avg=2.658 PF=1.914184345553066 | test n=11 avg=-3.247 PF=0.3867742400293148
- FLOW_MOM_0.3_3.0_S | maker pen=0 | 600s 10/20 | train n=23 avg=17.733 PF=8.102816812608676 | val n=5 avg=6.292 PF=2.422642234200322 | test n=11 avg=-3.762 PF=0.2335906487326154
- FLOW_MOM_0.3_3.0_S | maker pen=0 | 600s 8/16 | train n=23 avg=17.350 PF=7.78850756935894 | val n=5 avg=4.967 PF=2.4736653167217515 | test n=11 avg=-2.805 PF=0.2901365748608332
- FLOW_MOM_0.3_3.0_S | maker pen=1 | 300s 8/16 | train n=23 avg=17.100 PF=9.721162637438537 | val n=5 avg=0.668 PF=1.230623134818599 | test n=11 avg=-3.486 PF=0.3257674228423677
- FLOW_MOM_0.3_3.0_S | maker pen=1 | 300s 10/20 | train n=23 avg=16.892 PF=9.921348923940984 | val n=5 avg=1.658 PF=1.4727480727203923 | test n=11 avg=-4.247 PF=0.2839735887800132
- FLOW_MOM_0.3_3.0_S | maker pen=1 | 600s 10/20 | train n=23 avg=16.733 PF=6.783124516174764 | val n=5 avg=5.292 PF=2.0972995697922165 | test n=11 avg=-4.762 PF=0.15342390270794187
- FLOW_MOM_0.3_3.0_S | maker pen=1 | 600s 8/16 | train n=23 avg=16.350 PF=6.457120745058892 | val n=5 avg=3.967 PF=2.052129298484858 | test n=11 avg=-3.805 PF=0.1848643788664034
- FLOW_MOM_0.3_3.0_S | maker pen=2 | 300s 8/16 | train n=23 avg=16.100 PF=7.709261303162632 | val n=5 avg=-0.332 PF=0.9051260638026867 | test n=11 avg=-4.486 PF=0.2274462882315624
- FLOW_MOM_0.3_3.0_S | maker pen=2 | 300s 10/20 | train n=23 avg=15.892 PF=7.813683074483617 | val n=5 avg=0.658 PF=1.16026445368484 | test n=11 avg=-5.247 PF=0.20109365271917282
- FLOW_MOM_0.3_3.0_S | maker pen=0 | 300s 5/10 | train n=23 avg=15.872 PF=6.944448521955895 | val n=5 avg=-1.926 PF=0.5117165613799463 | test n=11 avg=-2.209 PF=0.42293753808243567
- FLOW_MOM_0.3_3.0_S | maker pen=2 | 600s 10/20 | train n=23 avg=15.733 PF=5.727189893237363 | val n=5 avg=4.292 PF=1.8217912865368497 | test n=11 avg=-5.762 PF=0.10326952699062035
- FLOW_MOM_0.3_3.0_S | maker pen=2 | 600s 8/16 | train n=23 avg=15.350 PF=5.418086897661263 | val n=5 avg=2.967 PF=1.7114508342615562 | test n=11 avg=-4.805 PF=0.1213343297438867
- ABSREV_0.1_4.0_S | maker pen=0 | 600s 10/20 | train n=46 avg=15.078 PF=7.240781559970258 | val n=15 avg=4.646 PF=2.1650262669513696 | test n=23 avg=-0.917 PF=0.7651821745728803
- ABSREV_0.2_4.0_S | maker pen=0 | 600s 10/20 | train n=46 avg=15.078 PF=7.240781559970258 | val n=15 avg=4.646 PF=2.1650262669513696 | test n=23 avg=-0.925 PF=0.7636661364445012
- ABSREV_0.3_4.0_S | maker pen=0 | 600s 10/20 | train n=46 avg=15.078 PF=7.240781559970258 | val n=15 avg=4.646 PF=2.1650262669513696 | test n=23 avg=-0.925 PF=0.7636661364445012
- FLOW_MOM_0.3_3.0_S | maker pen=3 | 300s 8/16 | train n=23 avg=15.100 PF=6.17850342337639 | val n=5 avg=-1.332 PF=0.687933225887625 | test n=11 avg=-5.486 PF=0.1485463071714047
- ABSREV_0.1_4.0_S | maker pen=0 | 600s 5/10 | train n=46 avg=15.009 PF=8.451754309541396 | val n=15 avg=3.914 PF=2.8414186468010194 | test n=23 avg=1.344 PF=1.4812013849671446
- ABSREV_0.2_4.0_S | maker pen=0 | 600s 5/10 | train n=46 avg=15.009 PF=8.451754309541396 | val n=15 avg=3.914 PF=2.8414186468010194 | test n=23 avg=1.352 PF=1.4853557013531062
- ABSREV_0.3_4.0_S | maker pen=0 | 600s 5/10 | train n=46 avg=15.009 PF=8.451754309541396 | val n=15 avg=3.914 PF=2.8414186468010194 | test n=23 avg=1.352 PF=1.4853557013531062

## Safety
No production execution was modified. No live orders were submitted. Promotion remains blocked. Session/regime matrices are diagnostic and not independent validation.