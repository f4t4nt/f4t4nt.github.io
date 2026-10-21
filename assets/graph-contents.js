(() => {
  const links = [...document.querySelectorAll('.graph-contents li a')];
  const headings = links.map(link => document.querySelector(link.hash));
  let pending = false;
  const update = () => {
    let current = -1;
    headings.forEach((heading, index) => {
      if (heading.getBoundingClientRect().top < 180) current = index;
    });
    links.forEach((link, index) => {
      if (index === current) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
    pending = false;
  };
  const scheduleUpdate = () => {
    if (!pending) { pending = true; requestAnimationFrame(update); }
  };
  document.addEventListener('scroll', scheduleUpdate, {passive: true});
  window.addEventListener('resize', scheduleUpdate);
  document.fonts.ready.then(scheduleUpdate);
  update();
})();
