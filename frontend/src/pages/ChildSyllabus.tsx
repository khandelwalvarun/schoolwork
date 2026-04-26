/**
 * Syllabus page — three-tab redesign.
 *
 *   Subjects (default)  subject-as-row, cycles-as-columns; the at-a-
 *                       glance trajectory view
 *   Cycle               this-week focus: cycle progress + decaying list
 *                       + per-subject coverage progress
 *   List                everything in one scroll, subject-grouped
 *
 * Filter strip (language + state) applies to all three tabs.
 * Persistent legend strip at viewport bottom.
 * Click any topic → TopicDetailPanel slide-over.
 *
 * Keyboard:
 *   1/2/3   switch tab
 *   /       focus filter (placeholder; filter strip is button-driven)
 *   Esc     close detail panel
 */
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import ChildHeader from "../components/ChildHeader";
import { TopicDetailPanel } from "../components/TopicDetailPanel";
import { MasteryLegend } from "../components/MasteryLegend";
import {
  emptyFilters,
  SyllabusFilters,
  SyllabusFilterState,
  langOf,
  filterTopic,
} from "../components/SyllabusFilters";
import { SubjectsView } from "../components/syllabus/SubjectsView";
import { CycleView } from "../components/syllabus/CycleView";
import { ListView } from "../components/syllabus/ListView";
import { todayISOInIST } from "../util/ist";

type Tab = "subjects" | "cycle" | "list";

const TAB_META: Array<{ key: Tab; label: string; key_hint: string }> = [
  { key: "subjects", label: "Subjects", key_hint: "1" },
  { key: "cycle",    label: "Cycle",    key_hint: "2" },
  { key: "list",     label: "List",     key_hint: "3" },
];

export default function ChildSyllabus() {
  const { id } = useParams();
  const childId = Number(id);

  const { data: child } = useQuery({
    queryKey: ["child-detail", childId],
    queryFn: () => api.childDetail(childId),
    enabled: !isNaN(childId),
  });
  const classLevel = child?.child.class_level;

  const { data: syl } = useQuery({
    queryKey: ["syllabus", classLevel],
    queryFn: () => api.syllabus(classLevel!),
    enabled: classLevel !== undefined,
  });
  const { data: topicStates } = useQuery({
    queryKey: ["topic-state", childId],
    queryFn: () => api.topicState(childId),
    enabled: !isNaN(childId),
  });

  const [tab, setTab] = useState<Tab>("subjects");
  const [filters, setFilters] = useState<SyllabusFilterState>(emptyFilters());
  const [openTopic, setOpenTopic] = useState<{
    subject: string;
    topic: string;
  } | null>(null);

  const todayISO = useMemo(() => todayISOInIST(), []);

  // Tab keyboard shortcuts: 1, 2, 3.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (e.key === "1") setTab("subjects");
      else if (e.key === "2") setTab("cycle");
      else if (e.key === "3") setTab("list");
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Topic count + shown count for the filter strip readout.
  const { totalTopics, shownTopics } = useMemo(() => {
    if (!syl || !topicStates) return { totalTopics: 0, shownTopics: 0 };
    const stateBy = new Map<string, (typeof topicStates)[number]>();
    for (const r of topicStates) stateBy.set(`${r.subject}::${r.topic}`, r);
    let total = 0;
    let shown = 0;
    for (const c of syl.cycles) {
      for (const [subj, topics] of Object.entries(c.topics_by_subject || {})) {
        for (const t of topics) {
          total++;
          const ms = stateBy.get(`${subj}::${t}`);
          const cov = (c.topic_status?.[subj]?.[t]?.status ?? null) as
            | "covered"
            | "in_progress"
            | "delayed"
            | "skipped"
            | null;
          if (filterTopic(filters, langOf, subj, ms?.state ?? null, cov)) shown++;
        }
      }
    }
    return { totalTopics: total, shownTopics: shown };
  }, [syl, topicStates, filters]);

  if (!child || !syl || !topicStates) {
    return (
      <div>
        <ChildHeader title="Syllabus" />
        <div className="space-y-4" aria-hidden="true">
          <div className="surface p-4 space-y-3">
            <div className="skeleton h-4 w-40" />
            <div className="skeleton h-3 w-full" />
            <div className="skeleton h-3 w-5/6" />
          </div>
          <div className="surface p-4 space-y-3">
            <div className="skeleton h-4 w-44" />
            <div className="skeleton h-3 w-full" />
            <div className="skeleton h-3 w-2/3" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="pb-12">
      <ChildHeader title="Syllabus" />
      <div className="text-sm text-gray-500 mb-3">
        Class {classLevel}, school year {syl.school_year || "?"} ·
        <Link to="/settings/syllabus" className="ml-2 text-blue-700 hover:underline">
          Calibrate cycles →
        </Link>
      </div>

      {/* Tab strip */}
      <div className="flex items-center gap-1 mb-3 border-b border-[color:var(--line-soft)]">
        {TAB_META.map((t) => {
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={
                "px-3 py-1.5 text-sm border-b-2 -mb-px " +
                (active
                  ? "border-purple-600 text-purple-800 font-semibold"
                  : "border-transparent text-gray-600 hover:text-gray-900")
              }
              aria-current={active ? "page" : undefined}
            >
              {t.label}
              <span className="ml-1.5 kbd">{t.key_hint}</span>
            </button>
          );
        })}
      </div>

      <SyllabusFilters
        filters={filters}
        onChange={setFilters}
        topicCount={totalTopics}
        shownCount={shownTopics}
      />

      {tab === "subjects" && (
        <SubjectsView
          syllabus={syl}
          states={topicStates}
          childId={childId}
          todayISO={todayISO}
          filters={filters}
          onTopicClick={(s, t) => setOpenTopic({ subject: s, topic: t })}
        />
      )}
      {tab === "cycle" && (
        <CycleView
          syllabus={syl}
          states={topicStates}
          todayISO={todayISO}
          filters={filters}
          onTopicClick={(s, t) => setOpenTopic({ subject: s, topic: t })}
          onSwitchTab={setTab}
        />
      )}
      {tab === "list" && (
        <ListView
          syllabus={syl}
          states={topicStates}
          childId={childId}
          todayISO={todayISO}
          filters={filters}
          onTopicClick={(s, t) => setOpenTopic({ subject: s, topic: t })}
        />
      )}

      <MasteryLegend />

      {openTopic && (
        <TopicDetailPanel
          childId={childId}
          subject={openTopic.subject}
          topic={openTopic.topic}
          onClose={() => setOpenTopic(null)}
        />
      )}
    </div>
  );
}
