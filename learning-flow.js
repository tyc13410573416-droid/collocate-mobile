(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.CollocationLearningFlow = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var VERSION = 3;
  var MAX_TIME = 253402300799999;
  var serial = 0;

  function nowValue(value) {
    var valueMs = value instanceof Date ? value.getTime() : value === undefined ? Date.now() : value;
    if (!Number.isInteger(valueMs) || valueMs < 0 || valueMs > MAX_TIME) throw new Error('学习时间无效。');
    return valueMs;
  }
  function localDate(value) {
    var date = new Date(nowValue(value));
    return String(date.getFullYear()).padStart(4, '0') + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
  }
  function stateFields(state) {
    if (!state || !Array.isArray(state.cards)) throw new Error('词库状态无效。');
    if (!state.learning) state.learning = {};
    if (!Array.isArray(state.learningGroups)) state.learningGroups = [];
    if (!state.learningExtras) state.learningExtras = {};
    return state;
  }
  function findCard(state, id) {
    var value = state.cards.find(function (card) { return card.id === id; });
    if (!value) throw new Error('词伙不存在。');
    return value;
  }
  function findGroup(state, groupId) {
    var value = (state.learningGroups || []).find(function (group) { return group.id === groupId; });
    if (!value) throw new Error('学习组不存在。');
    return value;
  }
  function entry(state, id, at) {
    if (!Object.prototype.hasOwnProperty.call(state.learning, id)) {
      Object.defineProperty(state.learning, id, { enumerable: true, configurable: true, writable: true, value: {
        choicePassed: false, recognized: false, spellingPassed: false,
        choiceErrors: 0, recognitionErrors: 0, spellingErrors: 0, reviewErrors: 0,
        startedAt: at, startedDate: localDate(at), completedAt: null,
        scheduleLevel: 0, lastReviewDate: null, reviewDays: [], weak: false
      } });
    }
    return state.learning[id];
  }
  function unique(values) { return Array.from(new Set(values)); }
  function scope(value, fallback, max) {
    value = value === undefined || value === null || value === '' ? fallback : value;
    if (typeof value !== 'string' || !value.trim() || value.length > max || /[\u0000-\u001f]/.test(value)) throw new Error('学习分类无效。');
    return value.trim();
  }
  function groupSize(value) {
    value = value === undefined ? 10 : value;
    if (!Number.isInteger(value) || value < 1 || value > 200) throw new Error('每组词伙数量应为 1–200。');
    return value;
  }
  function item(id, stage) { return { id: id, stage: stage }; }
  function oldFlow(state, group) {
    var old = group.flow || {};
    var done = Array.isArray(old.spellingDone) ? old.spellingDone.filter(function (id) { return group.ids.indexOf(id) !== -1; }) : [];
    var doneSet = new Set(done), queue = [];
    var fullyDone = group.completedAt !== null && group.completedAt !== undefined && done.length === group.ids.length;
    if (fullyDone) return { version: VERSION, queue: [], dictation: [], dictationActive: false };
    done.forEach(function (id) {
      if (state.learning && state.learning[id]) {
        state.learning[id].spellingPassed = false;
        state.learning[id].completedAt = null;
      }
    });
    if (Array.isArray(old.queue)) {
      old.queue.forEach(function (value) {
        if (value && group.ids.indexOf(value.id) !== -1 && !doneSet.has(value.id)) queue.push(item(value.id, value.stage >= 1 && value.stage <= 3 ? value.stage : 1));
      });
    }
    var queued = new Set(queue.map(function (value) { return value.id; }));
    group.ids.forEach(function (id) {
      if (!doneSet.has(id) && !queued.has(id)) {
        var learned = state.learning && state.learning[id];
        queue.push(item(id, learned && learned.recognized ? 3 : learned && learned.choicePassed ? 2 : 1));
      }
    });
    return { version: VERSION, queue: queue, dictation: done, dictationActive: done.length >= 10 };
  }
  function getFlow(state, group) {
    if (!group.flow || group.flow.version !== VERSION) group.flow = oldFlow(state, group);
    if (!Array.isArray(group.flow.queue) || !Array.isArray(group.flow.dictation) || typeof group.flow.dictationActive !== 'boolean') throw new Error('学习队列格式无效。');
    return group.flow;
  }
  function finishedIds(state, group, flow) {
    var activeIds = new Set(flow.queue.map(function (value) { return value.id; }).concat(flow.dictation));
    return new Set(group.ids.filter(function (id) { return !activeIds.has(id) && state.learning[id] && state.learning[id].spellingPassed; }));
  }
  function completeIfEmpty(group, flow, at) {
    group.completedAt = flow.queue.length === 0 && flow.dictation.length === 0 && !flow.dictationActive ? (group.completedAt || at) : null;
  }
  function progress(state, groupId) {
    var group = findGroup(state, groupId), flow = getFlow(state, group), finished = finishedIds(state, group, flow), meaning = finished.size, recognition = finished.size;
    flow.queue.forEach(function (value) { if (value.stage >= 2) meaning += 1; if (value.stage >= 3) recognition += 1; });
    flow.dictation.forEach(function () { meaning += 1; recognition += 1; });
    return { meaning: { done: meaning, total: group.ids.length }, recognition: { done: recognition, total: group.ids.length }, spelling: { done: finished.size, total: group.ids.length }, dictation: { done: finished.size, total: group.ids.length }, complete: flow.queue.length === 0 && flow.dictation.length === 0 && !flow.dictationActive };
  }
  function current(state, groupId) {
    var group = findGroup(state, groupId), flow = getFlow(state, group), value = null, phase = 'complete', id = null;
    if (flow.dictationActive && flow.dictation.length) { id = flow.dictation[0]; phase = 'dictation'; }
    else if (flow.queue.length) { value = flow.queue[0]; id = value.id; phase = value.stage === 1 ? 'meaning' : value.stage === 2 ? 'recognition' : 'spelling'; }
    return { group: group, phase: phase, stage: phase === 'meaning' ? 1 : phase === 'recognition' ? 2 : phase === 'spelling' ? 3 : phase === 'dictation' ? 4 : 0, cardId: id, card: id ? findCard(state, id) : null, index: id ? group.ids.indexOf(id) : group.ids.length, total: group.ids.length, queueLength: flow.queue.length, dictationLength: flow.dictation.length, progress: progress(state, groupId) };
  }
  function active(state, options) {
    options = options || {};
    var topic = options.topic === undefined ? undefined : scope(options.topic, 'all', 80), day = options.day === undefined ? undefined : scope(options.day, 'all', 100);
    var group = (state.learningGroups || []).slice().reverse().find(function (value) { return !progress(state, value.id).complete && (topic === undefined || value.topic === topic) && (day === undefined || (value.day || 'all') === day); });
    return group ? current(state, group.id) : null;
  }
  function available(state, ids) {
    if (!Array.isArray(ids)) throw new Error('待学习词伙列表无效。');
    var assigned = new Set((state.learningGroups || []).flatMap(function (group) { return group.ids; }));
    return unique(ids).filter(function (id) { var card = findCard(state, id); return !assigned.has(id) && card.attempts === 0 && !(state.learning[id] && state.learning[id].spellingPassed); });
  }
  function ensure(state, eligibleIds, options) {
    options = options || {};
    var at = nowValue(options.now), topic = scope(options.topic, 'all', 80), day = scope(options.day, 'all', 100), size = groupSize(options.size), resumed = active(state, { topic: topic, day: day });
    if (resumed) { stateFields(state); resumed.group.ids.forEach(function (id) { entry(state, id, at); }); return current(state, resumed.group.id); }
    var ids = available(state, eligibleIds).slice(0, size); if (!ids.length) return null;
    stateFields(state); var used = new Set(state.learningGroups.map(function (group) { return group.id; })), groupId;
    do { serial += 1; groupId = 'learn-' + at.toString(36) + '-' + serial.toString(36); } while (used.has(groupId));
    var group = { id: groupId, topic: topic, day: day, ids: ids, createdAt: at, updatedAt: at, completedAt: null, flow: { version: VERSION, queue: ids.map(function (id) { return item(id, 1); }), dictation: [], dictationActive: false } };
    ids.forEach(function (id) { entry(state, id, at); }); state.learningGroups.push(group); return current(state, groupId);
  }
  function answerStage(state, groupId, id, stage, correct, options, errorKey) {
    if (typeof correct !== 'boolean') throw new Error('学习反馈无效。');
    var at = nowValue(options && options.now), group = findGroup(state, groupId), flow = getFlow(state, group), head = flow.queue[0];
    if (!head || head.id !== id || head.stage !== stage) throw new Error('当前词伙不在对应学习阶段。');
    var learned = entry(state, id, at); flow.queue.shift();
    if (correct && stage < 3) { if (stage === 1) learned.choicePassed = true; else learned.recognized = true; flow.queue.push(item(id, stage + 1)); }
    else if (correct) { learned.choicePassed = true; learned.recognized = true; learned.spellingPassed = false; learned.completedAt = null; flow.dictation.push(id); if (flow.dictation.length === 10) flow.dictationActive = true; }
    else { learned[errorKey] += 1; learned.choicePassed = false; learned.recognized = false; learned.spellingPassed = false; learned.completedAt = null; flow.queue.push(item(id, 1)); }
    group.updatedAt = at; completeIfEmpty(group, flow, at); return current(state, groupId);
  }
  function chooseMeaning(state, groupId, id, correct, options) { return answerStage(state, groupId, id, 1, correct, options, 'choiceErrors'); }
  function recognize(state, groupId, id, correct, options) { return answerStage(state, groupId, id, 2, correct, options, 'recognitionErrors'); }
  function completeStage3(state, groupId, id, correct, options) { return answerStage(state, groupId, id, 3, correct, options, 'spellingErrors'); }
  function completeDictation(state, groupId, id, correct, options) {
    if (typeof correct !== 'boolean') throw new Error('学习反馈无效。');
    var at = nowValue(options && options.now), group = findGroup(state, groupId), flow = getFlow(state, group), learned = entry(state, id, at);
    if (!flow.dictationActive || flow.dictation[0] !== id) throw new Error('当前词伙不在整体听写中。');
    flow.dictation.shift();
    if (correct) { learned.spellingPassed = true; learned.completedAt = at; }
    else { learned.spellingErrors += 1; learned.choicePassed = false; learned.recognized = false; learned.spellingPassed = false; learned.completedAt = null; flow.queue.push(item(id, 1)); }
    if (!flow.dictation.length) flow.dictationActive = false;
    group.updatedAt = at; completeIfEmpty(group, flow, at); return current(state, groupId);
  }
  function addExtra(state, eligibleIds, count, options) {
    options = options || {}; var at = nowValue(options.now), group = options.groupId ? findGroup(state, options.groupId) : state.learningGroups[state.learningGroups.length - 1];
    if (!group) throw new Error('请先开始一个学习组。');
    var additions = available(state, eligibleIds).slice(0, groupSize(count)); if (!additions.length) return { addedCount: 0, ids: [], current: current(state, group.id) };
    var flow = getFlow(state, group); additions.forEach(function (id) { entry(state, id, at); group.ids.push(id); flow.queue.push(item(id, 1)); });
    group.completedAt = null; group.updatedAt = at; var day = localDate(at); state.learningExtras[day] = (state.learningExtras[day] || 0) + additions.length;
    return { addedCount: additions.length, ids: additions, current: current(state, group.id) };
  }
  function meaningOptions(state, id, options) {
    options = options || {}; var target = findCard(state, id), rng = options.rng || Math.random, seen = new Set([target.zh]), same = [], other = [];
    state.cards.forEach(function (card) { if (seen.has(card.zh)) return; seen.add(card.zh); (card.topic === target.topic ? same : other).push(card.zh); });
    function shuffle(values) { for (var i = values.length - 1; i > 0; i -= 1) { var j = Math.floor(rng() * (i + 1)), temp = values[i]; values[i] = values[j]; values[j] = temp; } return values; }
    return shuffle([target.zh].concat(shuffle(same).concat(shuffle(other)).slice(0, 3)));
  }
  function resetCard(state, id, options) {
    var at = nowValue(options && options.now); findCard(state, id); stateFields(state); var changed = 0;
    state.learningGroups.forEach(function (group) { if (group.ids.indexOf(id) === -1) return; var flow = getFlow(state, group); flow.queue = flow.queue.filter(function (value) { return value.id !== id; }); flow.dictation = flow.dictation.filter(function (value) { return value !== id; }); flow.queue.push(item(id, 1)); if (!flow.dictation.length) flow.dictationActive = false; var learned = entry(state, id, at); learned.choicePassed = false; learned.recognized = false; learned.spellingPassed = false; learned.completedAt = null; group.completedAt = null; group.updatedAt = at; changed += 1; });
    return changed;
  }
  function acknowledgeMeaning(state, groupId) { return current(state, groupId); }
  function acknowledgeRecognition(state, groupId) { return current(state, groupId); }
  function completeSpelling(state, groupId, id, correct, options) { return current(state, groupId).phase === 'dictation' ? completeDictation(state, groupId, id, correct, options) : completeStage3(state, groupId, id, correct, options); }
  return { version: VERSION, ensure: ensure, start: ensure, active: active, current: current, progress: progress, chooseMeaning: chooseMeaning, acknowledgeMeaning: acknowledgeMeaning, recognize: recognize, acknowledgeRecognition: acknowledgeRecognition, completeStage3: completeStage3, completeDictation: completeDictation, completeSpelling: completeSpelling, spellingReady: function (state, groupId) { var phase = current(state, groupId).phase; return phase === 'spelling' || phase === 'dictation'; }, addExtra: addExtra, meaningOptions: meaningOptions, resetCard: resetCard };
});
