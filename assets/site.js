const bar = document.querySelector(".progress");
if (bar) {
  const root = document.documentElement;
  const update = () => {
    const span = root.scrollHeight - root.clientHeight;
    const done = span > 0 ? root.scrollTop / span : 0;
    bar.style.transform = `scaleX(${Math.min(1, Math.max(0, done))})`;
  };
  addEventListener("scroll", update, { passive: true });
  update();
}
