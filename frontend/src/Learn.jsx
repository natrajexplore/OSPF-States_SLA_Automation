import { useState } from "react";
import { TOPICS, LEVELS } from "./learnContent.js";

function Block({ b }) {
  if (typeof b === "string") return <p>{b}</p>;
  if (b.h) return <h4>{b.h}</h4>;
  if (b.ul) return <ul>{b.ul.map((li, i) => <li key={i}>{li}</li>)}</ul>;
  if (b.code) return <pre>{b.code}</pre>;
  return null;
}

export default function Learn({ goToScenarios }) {
  const [topicId, setTopicId] = useState(TOPICS[0].id);
  const [level, setLevel] = useState("beginner");
  const topic = TOPICS.find((t) => t.id === topicId) || TOPICS[0];

  return (
    <>
      <section className="card">
        <h3>Learn OSPF</h3>
        <p className="muted small">
          A reference for each concept this lab demonstrates, at three depth levels. Pick a topic, then a level -
          each links to the scenario(s) on the Scenarios tab that let you see it happen live instead of just reading
          about it.
        </p>
        <div className="chips">
          {TOPICS.map((t) => (
            <button key={t.id} className={t.id === topicId ? "" : "secondary"} onClick={() => setTopicId(t.id)}>
              {t.title}
            </button>
          ))}
        </div>
      </section>
      <section className="card">
        <h3>
          {topic.title}
          <span className="spacer" />
          {LEVELS.map((l) => (
            <button key={l.id} className={l.id === level ? "" : "secondary"} onClick={() => setLevel(l.id)}>
              {l.label}
            </button>
          ))}
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
    </>
  );
}
