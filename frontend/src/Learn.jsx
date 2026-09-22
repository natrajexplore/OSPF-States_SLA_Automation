import { useEffect, useMemo, useState } from "react";
import { TOPICS, LEVELS } from "./learnContent.js";

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
