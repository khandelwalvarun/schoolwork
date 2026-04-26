# Parent Cockpit — Research on Evidence-Based Pedagogy & Monitoring

Compiled for two CBSE-track learners (Class 4 and Class 6) at Vasant Valley
School, Delhi. Each section has sourced takeaways, concrete cockpit-design
implications, and an honest call on what's overhyped.

---

## 1. Evaluation & Assessment Philosophy

**Sourced takeaways**

- **Formative assessment dwarfs summative on learning gains.** Black & Wiliam's
  1998 review of ~250 studies (Phi Delta Kappan, "Inside the Black Box") found
  typical effect sizes of d = 0.4–0.7 from strengthening formative assessment —
  larger than nearly any other educational intervention, and disproportionately
  helpful to low attainers.
  ([Black & Wiliam 1998 PDF](https://people.bath.ac.uk/edspd/Weblinks/MA_Ass/Resources/Using%20assessment%20formatively/Black%20&%20Wiliam%201998%20PDK.pdf))
- **Mastery learning is real but smaller than Bloom claimed.** Kulik et al.'s
  meta-analysis pegs mastery learning at ~d = 0.5 (50th → ~70th percentile),
  with bigger gains for less-able students (d = 0.61) than able ones (d = 0.4).
  The famous "two-sigma" effect did not replicate at scale.
  ([Kulik 1990](https://journals.sagepub.com/doi/10.3102/00346543060002265);
  [Nintil review](https://nintil.com/bloom-sigma/))
- **Grades-only assessment actively undermines intrinsic motivation.** Kohn
  synthesizes ~70 studies showing extrinsic incentives reduce interest,
  performance, and quality of work once removed.
  ([Kohn, Punished by Rewards](https://www.alfiekohn.org/punished-rewards/))
- **Standards-based / Marzano grading.** Robust empirical support for
  separating formative scores from summative averages and reporting against
  specific learning standards rather than a single percentage; averaging
  formative scores into summatives is explicitly contraindicated.
  ([Marzano Resources](https://www.marzanoresources.com/assessment-grading.html);
  [ERIC](https://files.eric.ed.gov/fulltext/ED590391.pdf))
- **Hattie & Timperley feedback levels.** Process-level and self-regulation
  feedback produce d ≈ 0.7. Task-level "right/wrong" or self/personal feedback
  ("you're smart") is much weaker.
  ([Wisniewski et al. 2020](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2019.03087/full))

**What the cockpit should add (data/UI)**

- Parse and tag every grade as **formative vs summative** so the dashboard
  does not average a 3-mark dictation with a term test.
- Surface graded items at a **standard/topic level**, not just an assignment
  level — e.g. "Tejas: Fractions = 3/4 proficient on last 5 items".
- Allow parent + child to attach a **portfolio artifact** (photo of a project,
  a drawing, a scanned essay) to a syllabus topic.
- Hide or de-emphasize raw % when there are <3 data points; show a confidence
  band instead.

**Overhyped / wrong**

- Letting any single percentage drive a parent's emotional state.
- Learning styles (VAK etc.) — four+ meta-analyses show effect sizes ~0.
  ([Yale Poorvu Center](https://poorvucenter.yale.edu/teaching/teaching-resource-library/learning-styles-as-a-myth);
  [Education Next](https://www.educationnext.org/stubborn-myth-learning-styles-state-teacher-license-prep-materials-debunked-theory/))

---

## 2. Per-Kid Progress Tracking — Skill Models

**Sourced takeaways**

- **Khan Academy uses simple heuristics.** "Attempted → Familiar → Proficient
  → Mastered" map to N-correct-in-a-row policies; provably near-optimal under
  the BKT model. No need for deep nets.
  ([Khan Academy mastery](https://support.khanacademy.org/hc/en-us/articles/5548760867853--How-do-Khan-Academy-s-Mastery-levels-work);
  [BKT vs DKT, JEDM](https://files.eric.ed.gov/fulltext/EJ1195512.pdf))
- **Duolingo's Half-Life Regression.** Settles & Meeder (ACL 2016) treat each
  item as having an exponential half-life in memory, fit a regression on lag,
  item difficulty and history. ~9.5 % retention lift in A/B over Leitner.
  ([Settles & Meeder 2016](https://research.duolingo.com/papers/settles.acl16.pdf);
  [GitHub](https://github.com/duolingo/halflife-regression))
- **Zone of Proximal Development.** Vygotsky's "can do with help"; meta-analysis
  shows scaffolding with **explicit fading protocols** produces d = 0.71 vs
  d = 0.32 when scaffolds remain constant.
  ([Verenikina, AARE](https://www.aare.edu.au/data/publications/2003/ver03682.pdf))
- **DKT vs BKT.** Deep Knowledge Tracing beats BKT on AUC for next-question
  correctness, but BKT actually wins for predicting **post-test** scores and
  is interpretable. With N=2 children there is no point fitting DKT.

**What the cockpit should add**

- A per-skill state object: `{topic, kid, last_assessed, last_score, attempts,
  current_state ∈ {attempted, familiar, proficient, mastered, decaying}}` —
  start with Khan-style heuristics.
- A **topic decay timer** based on the half-life concept: even a "mastered"
  topic should turn yellow if it has not been touched in N×half-life days.
- A "ZPD next step" view: for each subject, surface the next 1–2 topics the
  syllabus says are upcoming where prereqs look weak.

**Overhyped / wrong**

- DKT in production for a single-classroom dashboard. With N=2 and limited
  events, stick to heuristics + transparent rules.

---

## 3. Spaced Repetition, Retrieval Practice, Interleaving

**Sourced takeaways**

- **Testing effect.** Karpicke & Roediger (2008, Science) — repeated retrieval
  beats repeated study by a wide margin; gains visible at 1 week and 6 months.
  ([Karpicke & Roediger 2007 JML](https://learninglab.psych.purdue.edu/downloads/2007/2007_Karpicke_Roediger_JML.pdf))
- **Optimal spacing rule.** Cepeda et al. (2008): optimal review gap is
  ~10–20 % of the desired retention interval (e.g., for a 6-week test, review
  every ~5–10 days).
  ([Cepeda et al. 2008](https://laplab.ucsd.edu/articles/Cepeda%20et%20al%202008_psychsci.pdf))
- **Interleaving in math.** Rohrer & Taylor: 4th graders interleaving math
  problems scored 77 % vs 38 % (d = 1.21) on a delayed test.
  ([Rohrer & Taylor 2007](http://uweb.cas.usf.edu/~drohrer/pdfs/Rohrer&Taylor2007IS.pdf))
- **Bjork's "desirable difficulties."** Conditions that *feel harder* during
  practice reliably produce better long-term retention.
  ([Bjork & Bjork 2011](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf))

**What the cockpit should add**

- A **review queue** at the topic level. For every syllabus topic with at
  least one graded data point, compute
  `next_review_at = last_seen + f(score, retention_target)` using a
  Cepeda-style ratio (~15 % of horizon).
- A **"shaky topics" tray**: 2–3 max per kid per week.
- An **interleaving nudge** when a math/science test is detected: mix problem
  types, especially across already-graded topics.

**Overhyped / wrong**

- Rote SM-2 / Anki style scheduling for school content. Use the spacing
  *idea*, not the *UX*.

---

## 4. Parent Involvement Research

**Sourced takeaways**

- **Hill & Tyson (2009) middle-school meta-analysis.** Across 50 studies the
  strongest correlate of achievement was **academic socialization** (talking
  about school, future plans, conveying expectations): r = +0.39.
  **Direct homework help was negative**: r = −0.11.
  ([Hill & Tyson 2009 APA](https://www.apa.org/pubs/journals/releases/dev453740.pdf))
- **Patall, Cooper & Robinson (2008).** ~⅔ of parents give "unconstructive"
  homework assistance.
  ([Patall et al. 2008](https://journals.sagepub.com/doi/abs/10.3102/0034654308325185))
- **Helicopter parenting.** Meta-analysis of 53 studies: linked to
  **decreased** academic adjustment, self-efficacy, and self-regulation.
  ([Springer 2024](https://link.springer.com/article/10.1007/s10804-024-09496-5))
- **Hattie's effect size.** Parental involvement overall sits at d ≈ 0.50 —
  but only specific types work; it's not a monolith.

**What the cockpit should add**

- A "**Talk about it**" prompt instead of a "Do it with them" prompt.
- Capture and surface **conversation starters**: 1–2 sentence summaries of
  what the kid did this week. Designed for a 5-minute dinner-table chat.

**What the cockpit should NOT do**

- Auto-suggest "do this assignment together."
- Send the parent every grade in real time. Pushes toward intrusive,
  controlling behaviors.

---

## 5. Effort & Struggle Signals From Log Data

**Sourced takeaways**

- **Sentiment analysis on teacher comments has measurable predictive lift.**
  ([JCHE 2023](https://link.springer.com/article/10.1007/s12528-023-09370-5))
- **MOOC dropout prediction is fragile under replication.** Be cautious with
  any "predicted at-risk" label.
- **Most predictive features are simple counts**: accumulated credits, failed
  course count, LMS activity count.
- **Working memory matures unevenly.** A Class-4 child has ~4-item span; the
  same observable behavior can be capacity ceiling, not effort failure.

**What the cockpit should add**

- **Lateness pattern**, not just lateness.
- **Repeated-attempt counter** on the audit log.
- **Weekend cramming detector**: events created Saturday/Sunday for items due
  Monday.
- **Teacher-comment polarity trend**, not raw sentiment score.

**Overhyped / wrong**

- Single-event "this child is at risk" predictions.
- Time-to-complete as a quality signal in isolation.

---

## 6. Notification & Intervention Design

**Sourced takeaways**

- **Calm Technology** (Weiser & Brown, 1995): tech should "inform but not
  demand attention."
  ([Calm Technology PDF](https://people.csail.mit.edu/rudolph/Teaching/weiser.pdf))
- **Hattie–Timperley feedback model**: feedback works at process or
  self-regulation level, not when it's task-level "you got X% wrong." Most
  parent-app pings are exactly the worst kind.
- **Learning analytics dashboards** work best when each datum is co-traceable
  to its source.

**What the cockpit should add**

- **Three notification tiers**:
  - **Now**: only school-issued urgent. Rare, push.
  - **Today**: at most one digest per kid per day.
  - **Weekly**: a Sunday brief with conversation starters.
- A **"why this nudge?" link** on every alert.
- **Silence by default** for any score >75 % on a single assignment unless
  trend is downward.

---

## 7. Indian / CBSE / IGCSE Context

**Sourced takeaways**

- **CBSE has explicit homework caps:** no homework Class I–II; up to **2 hours
  /week** Classes III–V; up to **1 hour/day** Classes VI–VIII. Many schools
  exceed this.
  ([EuroSchool summary](https://www.euroschoolindia.com/blogs/homework-policy-for-cbse-students-according-to-ncert/);
  [CBSE Circular 52/2020](https://cbseacademic.nic.in/web_material/Circulars/2020/52_Circular_2020.pdf))
- **Cooper meta-analysis is consistent with CBSE's caps.** For elementary
  students, more homework time *predicts lower* achievement.
- **Stress in CBSE schools is high.** A 2025 Belagavi-district survey of
  1,426 CBSE students: 74 % report high academic stress; 66 % feel parental
  pressure.
  ([Frontiers 2025](https://www.frontiersin.org/journals/public-health/articles/10.3389/fpubh.2025.1631136/full))
- **Three-language formula matters**: Hindi, English, often Sanskrit at this
  school. ESL/multi-language load is real.

**What the cockpit should add**

- A per-kid **time-on-homework counter** with the CBSE caps as a horizon line.
  If Sam is logging 2.5 hr/day, that is *above* the 2 hr/week guidance and is
  a parent-talk-to-school signal.
- **Language-specific tracking**. Don't blend English / Hindi / Sanskrit into
  one "Languages" sparkline.
- A **stress proxy**: weekend-evening cramming + repeated-attempt + late-night
  activity. Surface quietly — *not* as an alert.

---

## 8. Self-Regulation & Metacognition (the kid's view)

**Sourced takeaways**

- **Zimmerman's three-phase cycle**: forethought → performance → self-
  reflection. Skill is built when the same student moves through all three
  repeatedly.
  ([Zimmerman 2002](https://www.leiderschapsdomeinen.nl/wp-content/uploads/2016/12/Zimmerman-B.-2002-Becoming-Self-Regulated-Learner.pdf))
- **EEF rates metacognition + self-regulation at +8 months progress, low
  cost** — the highest-impact-per-dollar intervention in their toolkit.
  ([EEF Toolkit](https://educationendowmentfoundation.org.uk/education-evidence/teaching-learning-toolkit/metacognition-and-self-regulation))
- **Direct-instruction works for metacognition with young kids too.** Class-4
  (age 9) is well within the effective range.
  ([Springer 2024](https://link.springer.com/article/10.1007/s11409-024-09405-x))

**What the cockpit should add**

- A **kid-facing "today" view**: *plan* (tick what you'll do today),
  *mid-check* (one face-emoji how it's going), *reflect* (1-line "what was
  hard?"). Zimmerman's loop in 30 seconds. Highest-ROI build.
- A **per-kid prediction question** before each test, then compare to the
  actual graded score.
- A **reflect-after-grade** prompt (one tap: "I expected this / better /
  worse").

**Overhyped / wrong**

- Growth-mindset interventions. Sisk et al. (2018) and Case Western
  replication found benefits "largely overstated."
  ([ScienceDaily](https://www.sciencedaily.com/releases/2018/05/180522114523.htm))

---

## Prioritized Feature Backlog (most → least leverage)

| # | Feature | Why (research basis) | How in this app |
|---|---------|----------------------|-----------------|
| 1 | **Topic-level state model with decay** (Khan-style heuristics + half-life decay) | Mastery learning d ≈ 0.5; spacing effect. Currently grades exist but no per-topic state. | Promote `syllabus → cycles → subjects → topics`: each topic gets a state computed from grades + assignments tagged to it; render colored dots in kid pages. |
| 2 | **Sunday parent brief** with academic-socialization conversation starters | Hill & Tyson: academic socialization r = +0.39; calm tech; minimises helicopter risk. | New view + scheduled digest job; reuse existing search + audit drawer. Push only urgents day-of; everything else waits for Sunday. |
| 3 | **Kid-facing daily Zimmerman loop** (plan / mid-check / reflect, 3 taps) | EEF: +8 months progress, lowest cost. Effective from age 5+. | Add per-kid view at `/kid/<id>/today` distinct from parent Today view. |
| 4 | **Spaced-review queue ("Shaky topics this week")** with Cepeda 10–20 % rule | Testing effect; spacing; honest about data sparsity. | Compute on top of #1; expose as new tray, capped 2–3 items per kid per week. |
| 5 | **Time-on-homework + CBSE-cap horizon** | Cooper: elementary HW time → ≤0 academic return. CBSE 2 hr/wk for III–V, 1 hr/day VI–VIII. | Sum durations from audit log; horizontal cap line on chart; if exceeded, surface "talk to school" not "do more." |
| 6 | **Notification tiering with explicit defaults (Now / Today / Weekly)** | Calm tech; notification fatigue; Hattie. | Refactor alerts into three channels; default high-grade alerts to weekly only. |
| 7 | **Lateness + repeated-attempt + weekend-cramming pattern detector** | Trend-based, defensible. | Already partially in audit log; add three boolean monthly features per kid; surface as quiet chart. |
| 8 | **Per-language tracking split** (English / Hindi / Sanskrit + future) | Indian three-language formula; ESL acquisition curves. Currently grades blend. | Tag each subject with a language code; split sparklines and topic-states. |
| 9 | **Self-prediction calibration loop** ("I expected … / I got …") | Metacognitive monitoring is the strongest of Zimmerman's three SRL processes. | One-tap before/after each test; new field on existing assignment record. |
| 10 | **Conversation-starter generator from teacher comments** (sentiment-trend, not score) | Sentiment in teacher language is signal; raw single comment is not. | Lexicon classifier locally over `comments`; expose in Sunday brief as "what's changed in tone." |
| 11 | **Why-this-nudge explainer + snooze on every alert** | Trust + dismissal reduction. | `(why?)` link on each notification → rule + data points + snooze/dismiss. |
| 12 | **Portfolio attachment per topic** | Multiliteracies; portfolio assessment ~41 % pre-post lift; multi-year multimodal record. | Reuse attachments pipeline; allow attachment on `syllabus.topic`. |

---

### Honest assessments

- **Single-percentage grades** are noisier than sparklines suggest.
- **Predictive ML** replicates poorly with N=2 children — resist beyond rule-
  based heuristics.
- **Growth-mindset and learning-styles features** would be wasted dev time.
- **Real-time alerting** is the default failure mode — the most evidence-based
  design choice is to *withhold* signal until it's part of a digest.
- **CBSE caps + Indian stress data** mean the cockpit's job is at least as
  much "tell parent the kid is doing too much" as "tell parent the kid is
  doing too little." Build for both directions.
