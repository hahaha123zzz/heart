// 复用固定上游的完整画布和 Manim 展示组件；宿主只适配挂载生命周期。
import React, {Suspense} from 'react';
import {createRoot} from 'react-dom/client';
import Viewer from '@/components/visualize/VisualizationViewer';
import {extractVisualizeResult} from '@/lib/visualize-types';
import {extractQuizQuestions} from '@/lib/quiz-types';
import {MasteryQuestionCard} from '@/components/chat/home/MasteryQuestionCard';
import {collectMasteryQuestions,collectMasteryGrades,collectMasterySkips} from '@/lib/mastery-question';
window.TutorNativeViewer = {
 mount(host, data) {
  host.classList.add('native-viewer');
  const root=createRoot(host);
  const update=(value)=>{
   const result=extractVisualizeResult(value);
   const questions=extractQuizQuestions(value) || [];
   const masteryQuestions=collectMasteryQuestions(value.mastery_events);
   const messages=value.masteryMessages || [{events:value.mastery_events || []}];
   const grades=collectMasteryGrades(messages), skips=collectMasterySkips(messages);
   root.render(<><Suspense fallback={<p>正在加载展示组件…</p>}>{result?<Viewer result={result}/>:null}</Suspense>
    {questions.map((question,index)=><section className="native-quiz-question" key={question.question_id || index}>
      <h3>练习题 {index+1}</h3>
      <div dangerouslySetInnerHTML={{__html:window.renderTutorAnswer(question.question)}}/>
      {Object.entries(question.options || {}).map(([key,text])=><p key={key}><strong>{key}. </strong>{text}</p>)}
    </section>)}
    {[...masteryQuestions.values()].map(question=><MasteryQuestionCard key={question.questionId}
      question={question} grade={grades.get(question.questionId) || null}
      answered={grades.has(question.questionId)} skipped={skips.has(question.questionId)}
      onSubmit={answer=>value.onMasteryAnswer?.(question.questionId,answer.text)}
      onSkip={questionId=>value.onMasterySkip?.(questionId)}/>)}
    {(value.workspace_items || []).map(item=><div key={item.workspace_item_id}>
      {item.mime_type?.startsWith('audio/')?<audio controls preload="metadata" src={item.url}/>:null}
      {item.mime_type?.startsWith('video/')?<video controls preload="metadata" src={item.url} style={{maxWidth:'100%'}}/>:null}
      {item.mime_type?.startsWith('image/')?<img src={item.url} alt={item.title || item.filename} style={{maxWidth:'100%'}}/>:null}
      <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title || item.filename}</a>
    </div>)}</>);
  };
  update(data);
  return {update,dispose:()=>root.unmount()};
 }
};
