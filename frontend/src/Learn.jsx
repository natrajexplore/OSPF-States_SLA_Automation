import { useEffect, useMemo, useState } from "react";
import { usePoll } from "./api.js";
import { TOPICS, LEVELS } from "./learnContent.js";
import { LEARN_LAB } from "./learnLab.js";
import { liveState } from "./liveState.js";
import Topo3D from "./Topo3D.jsx";

const STORAGE_KEY = "ospf-learn-progress";

function loadProgress() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

function saveProgress(p) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    // localStorage unavailable (private window, cleared storage, etc.) - progress just won't persist
  }
}

function unlocked(progress, topicId) {
  const p = progress[topicId] || {};
  return { beginner: true, pro: !!p.beginner, expert: !!p.pro };
}

function furthestUnlocked(progress, topicId) {
  const u = unlocked(progress, topicId);
  if (u.expert) return "expert";
  if (u.pro) return "pro";
  return "beginner";
}

function Block({ b }) {
  if (typeof b === "string") return <p>{b}</p>;
  if (b.h) return <h4>{b.h}</h4>;
  if (b.ul) return <ul>{b.ul.map((li, i) => <li key={i}>{li}</li>)}</ul>;
  if (b.code) return <pre>{b.code}</pre>;
  return null;
}

/** The topic in the real lab: a packet flow in 3D (one caption per router) and the topic's OSPF parameters. */
function InTheLab({ topicId, goToScenarios }) {
  const lab = LEARN_LAB[topicId];
  const { data: graph, error } = usePoll("/api/graph", 300000);
  const { data: monitor } = usePoll("/api/monitor/state", 10000);
  const [fi, setFi] = useState(0);
  const [hop, setHop] = useState(0);
  useEffect(() => { setFi(0); setHop(0); }, [topicId]);
  const af = lab?.af || "v4";
  const state = useMemo(() => liveState(graph, monitor, null, af), [graph, monitor, af]);
  if (!lab) return null;
  const flow = lab.flows[fi] || lab.flows[0];
  const live = (monitor || []).some((m) => m.reachable);
  const v6Up = (monitor || []).some((m) => m.neighbors_v6?.length);

  return (
    <section className="card">
      <h3>
        See it in the lab{" "}
        <span className="muted small">
          {!live ? "preview (lab not answering)" : af === "v6"
            ? (v6Up ? "live OSPFv3 adjacencies" : "OSPFv3 is not running: links stay grey until 17_ospfv3_dual_stack is applied")
            : "live colours from the running lab"}
        </span>
      </h3>
      <div className="chips">
        {lab.flows.map((f, i) => (
          <button key={f.label} className={i === fi ? "" : "secondary"} onClick={() => { setFi(i); setHop(0); }}>{f.label}</button>
        ))}
      </div>
      {error && <div className="alert bad">Backend: {error}</div>}
      <div className="learn-3d">
        <Topo3D graph={graph} state={state} highlight={flow.highlight}
          trace={{ key: `${topicId}/${flow.label}`, path: flow.path, onHop: setHop }} height={380} />
        <ol className="hops">
          {flow.path.map((r, i) => (
            <li key={i} className={i === hop ? "on" : ""}><b>{r}</b> {flow.captions[i]}</li>
          ))}
        </ol>
      </div>
      <p className="muted small">
        {flow.scenario ? <>This is what scenario <code>{flow.scenario}</code> produces. </> : <>This is the lab at its baseline. </>}
        Amber routers are the ones the scenario configures.{" "}
        {flow.scenario && <button className="secondary small" onClick={() => goToScenarios?.(flow.scenario)}>Run {flow.scenario} →</button>}
      </p>
      <h4>Parameters of this topic</h4>
      <table className="params">
        <thead><tr><th>Parameter</th><th>Command</th><th>IOS default</th><th>Both ends must match?</th><th>In this lab</th><th>Changed by</th></tr></thead>
        <tbody>
          {lab.params.map(([name, cmd, def, match, val, sc]) => (
            <tr key={name}><td><b>{name}</b></td><td><code>{cmd}</code></td><td>{def}</td><td>{match}</td><td>{val}</td><td>{sc}</td></tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Quiz({ quizKey, questions, passed, onPass, unlocksLabel }) {
  const [answers, setAnswers] = useState({});
  const allCorrect = questions.every((q, i) => answers[i] === q.correct);

  useEffect(() => {
    setAnswers({});
  }, [quizKey]);

  useEffect(() => {
    if (allCorrect && !passed) onPass();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allCorrect, passed]);

  return (
    <section className="card quiz">
      <h3>
        Check your understanding
        {passed && <span className="badge ok">passed</span>}
      </h3>
      <p className="muted small">
        Get all {questions.length} right to unlock <strong>{unlocksLabel}</strong>
        {passed ? " - already unlocked, feel free to review." : "."}
      </p>
      {questions.map((q, qi) => {
        const picked = answers[qi];
        const isCorrect = picked === q.correct;
        return (
          <div className="quiz-q" key={qi}>
            <p><strong>{qi + 1}.</strong> {q.q}</p>
            <div className="chips">
              {q.options.map((opt, oi) => (
                <button
                  key={oi}
                  className={picked === oi ? (isCorrect ? "" : "danger") : "secondary"}
                  onClick={() => setAnswers((a) => ({ ...a, [qi]: oi }))}
                >
                  {opt}
                </button>
              ))}
            </div>
            {picked != null && (
              <p className={`small ${isCorrect ? "ok-text" : "bad-text"}`}>
                {isCorrect ? "Correct. " : "Not quite. "}{q.explain}
              </p>
            )}
          </div>
        );
      })}
    </section>
  );
}

export default function Learn({ goToScenarios }) {
  const [progress, setProgress] = useState(loadProgress);
  const [topicId, setTopicId] = useState(TOPICS[0].id);
  const [level, setLevel] = useState(() => furthestUnlocked(loadProgress(), TOPICS[0].id));
  const topic = TOPICS.find((t) => t.id === topicId) || TOPICS[0];
  const u = useMemo(() => unlocked(progress, topicId), [progress, topicId]);

  const pass = (lvl) => {
    setProgress((p) => {
      const next = { ...p, [topicId]: { ...p[topicId], [lvl]: true } };
      saveProgress(next);
      return next;
    });
  };

  const pickTopic = (id) => {
    setTopicId(id);
    setLevel(furthestUnlocked(progress, id));
  };

  const quiz = topic.quizzes?.[level];
  const nextLevelIdx = LEVELS.findIndex((l) => l.id === level) + 1;
  const nextLevelLabel = LEVELS[nextLevelIdx]?.label;

  return (
    <>
      <section className="card">
        <h3>Learn OSPF</h3>
        <p className="muted small">
          A reference for each concept this lab demonstrates, at three depth levels. Pass the short quiz at the end
          of Beginner and Pro to unlock the next level for that topic - progress is saved in this browser.
        </p>
        <div className="chips">
          {TOPICS.map((t) => {
            const tu = unlocked(progress, t.id);
            const done = tu.expert ? "✓ " : tu.pro ? "◐ " : "";
            return (
              <button key={t.id} className={t.id === topicId ? "" : "secondary"} onClick={() => pickTopic(t.id)}>
                {done}{t.title}
              </button>
            );
          })}
        </div>
      </section>
      <section className="card">
        <h3>
          {topic.title}
          <span className="spacer" />
          {LEVELS.map((l) => {
            const isUnlocked = u[l.id];
            return (
              <button
                key={l.id}
                className={l.id === level ? "" : "secondary"}
                disabled={!isUnlocked}
                title={isUnlocked ? "" : "Pass the previous level's quiz to unlock"}
                onClick={() => isUnlocked && setLevel(l.id)}
              >
                {isUnlocked ? "" : "🔒 "}{l.label}
              </button>
            );
          })}
        </h3>
        <p className="muted small">{topic.blurb}</p>
        {topic.scenarios.length > 0 && (
          <div className="chips">
            <span className="muted small">Try it live:</span>
            {topic.scenarios.map((sid) => (
              <button key={sid} className="secondary" onClick={() => goToScenarios?.(sid)}>
                {sid} {"→"}
              </button>
            ))}
          </div>
        )}
        <div className="learn-body">
          {topic[level].map((b, i) => <Block key={i} b={b} />)}
        </div>
      </section>
      <InTheLab topicId={topicId} goToScenarios={goToScenarios} />
      {quiz && nextLevelLabel && (
        <Quiz
          quizKey={`${topicId}-${level}`}
          questions={quiz}
          passed={!!u[LEVELS[nextLevelIdx].id]}
          onPass={() => pass(level)}
          unlocksLabel={nextLevelLabel}
        />
      )}
    </>
  );
}
