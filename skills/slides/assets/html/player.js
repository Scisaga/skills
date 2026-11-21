"use strict";

(() => {
  const timeline = JSON.parse(document.getElementById("timeline").textContent);
  const deck = document.getElementById("deck");
  const audio = document.getElementById("narration");
  const slider = document.getElementById("seek");
  const message = document.getElementById("message");
  const play = document.getElementById("play");
  const previous = document.getElementById("previous");
  const next = document.getElementById("next");
  const position = document.getElementById("position");
  const pages = [...deck.querySelectorAll(".page")];
  const layers = pages.map(page => new Map(
    [...page.querySelectorAll("[data-beat]")].map(element => [element.dataset.beat, element])
  ));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const wipe = { wipe_right: 1, wipe_down: 2, wipe_left: 3, wipe_up: 0 };
  let visible = new Set([0]);
  let index = 0;
  let time = 0;
  let frame = 0;
  let running = false;
  let generation = 0;

  function resize() {
    const rect = deck.getBoundingClientRect();
    const scale = document.body.dataset.view === "read"
      ? Math.min(1, deck.clientWidth / 1600)
      : Math.min(rect.width / 1600, rect.height / 900);
    deck.style.setProperty("--scale", String(scale));
  }

  function setVisible(indices) {
    for (const i of visible) if (!indices.includes(i)) pages[i].hidden = true;
    for (const i of indices) pages[i].hidden = false;
    visible = new Set(indices);
  }

  function showBeats(pageIndex, localTime) {
    return timeline.slides[pageIndex].beats.map(beat => {
      const target = layers[pageIndex].get(beat.id);
      if (!target) throw new Error("Missing animation target " + beat.id);
      const progress = clamp((localTime - beat.start_ms) / beat.duration_ms, 0, 1);
      target.style.visibility = progress === 0 ? "hidden" : "";
      if (beat.effect === "fade") {
        target.style.opacity = String(progress);
      } else {
        const inset = [0, 0, 0, 0];
        inset[wipe[beat.effect]] = (1 - progress) * 100;
        target.style.clipPath = progress === 1 ? "" : "inset(" + inset.map(p => p + "%").join(" ") + ")";
      }
      return progress;
    });
  }

  function updateControls() {
    slider.value = String(Math.round(time));
    position.textContent = (index + 1) + " / " + pages.length;
    previous.disabled = index === 0;
    next.disabled = index === pages.length - 1;
    play.textContent = running ? "暂停" : "播放";
  }

  function renderAt(milliseconds) {
    time = clamp(milliseconds, 0, timeline.total_ms);
    index = timeline.slides.findIndex(slide => time < slide.start_ms + slide.hold_ms + slide.transition_ms);
    if (index < 0) index = pages.length - 1;
    const slide = timeline.slides[index];
    const local = time - slide.start_ms;
    const progress = showBeats(index, local);
    pages[index].style.opacity = "1";
    pages[index].style.zIndex = "0";
    const crossing = local >= slide.hold_ms && slide.transition_ms > 0;
    if (crossing) {
      const following = index + 1;
      showBeats(following, 0);
      pages[following].style.opacity = String(clamp((local - slide.hold_ms) / slide.transition_ms, 0, 1));
      pages[following].style.zIndex = "1";
      setVisible([index, following]);
    } else {
      setVisible([index]);
    }
    updateControls();
    const stable = !crossing && progress.every(value => value === 0 || value === 1);
    return stable ? index + ":" + progress.join("") : null;
  }

  function showFinal(pageIndex) {
    index = pageIndex;
    time = timeline.slides[index].start_ms;
    showBeats(index, Infinity);
    pages[index].style.opacity = "1";
    pages[index].style.zIndex = "0";
    setVisible([index]);
    updateControls();
  }

  function stop() {
    generation++;
    running = false;
    if (audio) audio.pause();
    cancelAnimationFrame(frame);
    updateControls();
  }

  function showError(error) {
    message.textContent = error.message;
    message.hidden = false;
    stop();
  }

  async function start() {
    const token = ++generation;
    if (time >= timeline.total_ms) time = 0;
    running = true;
    updateControls();
    const startTime = performance.now() - time;
    if (audio) {
      audio.currentTime = time / 1000;
      try {
        await audio.play();
      } catch (error) {
        if (token === generation) throw error;
        return;
      }
      if (token !== generation) return;
    }
    const tick = now => {
      if (token !== generation) return;
      renderAt(audio ? (audio.ended ? timeline.total_ms : audio.currentTime * 1000) : now - startTime);
      if (time >= timeline.total_ms) stop();
      else frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
  }

  function jump(pageIndex) {
    const destination = clamp(pageIndex, 0, pages.length - 1);
    if (document.body.dataset.view === "read") {
      stop();
      index = destination;
      time = timeline.slides[index].start_ms;
      pages[index].scrollIntoView();
      updateControls();
      return;
    }
    const wasPlaying = running;
    stop();
    if (!wasPlaying && timeline.mode === "static_html") {
      showFinal(destination);
      return;
    }
    renderAt(timeline.slides[destination].start_ms);
    if (wasPlaying) start().catch(showError);
    else if (timeline.mode === "animated_html") {
      const token = generation;
      const slide = timeline.slides[index];
      const end = Math.max(0, ...slide.beats.map(beat => beat.start_ms + beat.duration_ms));
      const started = performance.now();
      const tick = now => {
        if (token !== generation) return;
        const local = Math.min(now - started, end);
        renderAt(slide.start_ms + local);
        if (local < end) frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    }
  }

  function stage(view) {
    document.body.dataset.view = view;
    resize();
  }

  function layoutFinal(indices) {
    setVisible(indices);
    for (const i of indices) {
      showBeats(i, Infinity);
      pages[i].style.opacity = "1";
      pages[i].style.zIndex = "0";
    }
  }

  function toggleRead() {
    stop();
    const reading = document.body.dataset.view === "read";
    stage(reading ? "play" : "read");
    if (reading) showFinal(index);
    else {
      layoutFinal(pages.map((_, i) => i));
      pages[index].scrollIntoView();
    }
    document.getElementById("read").textContent = reading ? "阅读" : "演示";
  }

  function togglePlay() {
    message.hidden = true;
    if (running) stop();
    else {
      if (document.body.dataset.view === "read") toggleRead();
      cancelAnimationFrame(frame);
      start().catch(showError);
    }
  }

  function toggleFullscreen() {
    const operation = document.fullscreenElement
      ? document.exitFullscreen()
      : document.documentElement.requestFullscreen();
    operation.catch(showError);
  }

  previous.onclick = () => jump(index - 1);
  next.onclick = () => jump(index + 1);
  play.onclick = togglePlay;
  document.getElementById("read").onclick = toggleRead;
  document.getElementById("fullscreen").onclick = toggleFullscreen;
  slider.max = String(timeline.total_ms);
  slider.oninput = () => {
    const destination = Number(slider.value);
    const resume = running;
    stop();
    if (document.body.dataset.view === "read") toggleRead();
    renderAt(destination);
    if (resume) start().catch(showError);
  };
  document.addEventListener("keydown", event => {
    if (event.target.closest("input, textarea, select, [contenteditable]")) return;
    if (event.key === " " && event.target.closest("button, a")) return;
    const action = {
      ArrowRight: () => jump(index + 1),
      ArrowLeft: () => jump(index - 1),
      " ": togglePlay,
      f: toggleFullscreen,
    }[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  });
  addEventListener("resize", resize);
  resize();
  showFinal(0);

  window.slides = {
    timeline,
    renderAt(milliseconds) {
      if (document.body.dataset.view !== "render") stage("render");
      return renderAt(milliseconds);
    },
    showFinal(i) {
      stage("render");
      showFinal(i);
    },
    printPages(indices) {
      stage("print");
      layoutFinal(indices);
      for (const i of indices) deck.append(pages[i]);
    },
  };
})();
