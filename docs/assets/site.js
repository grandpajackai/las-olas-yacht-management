(() => {
  'use strict';

  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));

  function setupStickyHeader() {
    const header = document.querySelector('.site-header');
    if (!header) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      header.classList.toggle('is-scrolled', window.scrollY > 80);
    };
    window.addEventListener('scroll', () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    }, { passive: true });
    update();
  }

  function setupMenu() {
    const toggle = document.getElementById('menu-toggle');
    const menu = document.getElementById('mobile-menu');
    if (!toggle || !menu) return;

    const mobile = window.matchMedia('(max-width: 900px)');
    const background = Array.from(document.querySelectorAll('main, .footer'));
    const previousInert = new Map();
    const closedLabel = toggle.getAttribute('aria-label') || 'Open navigation menu';
    const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    let open = false;

    const focusable = () => [toggle, ...menu.querySelectorAll(focusableSelector)].filter(element => element.getClientRects().length > 0 && !element.hidden);

    function setOpen(next, restoreFocus = true) {
      open = next && mobile.matches;
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Close navigation menu' : closedLabel);
      menu.classList.toggle('open', open);
      menu.setAttribute('aria-hidden', String(!open));
      menu.inert = !open;
      document.body.classList.toggle('menu-open', open);

      if (open) {
        background.forEach(element => {
          if (!previousInert.has(element)) previousInert.set(element, element.inert);
          element.inert = true;
        });
        const firstLink = menu.querySelector(focusableSelector);
        if (firstLink) firstLink.focus({ preventScroll: true });
      } else {
        previousInert.forEach((value, element) => { element.inert = value; });
        previousInert.clear();
        if (restoreFocus) toggle.focus({ preventScroll: true });
      }
    }

    setOpen(false, false);
    toggle.addEventListener('click', () => setOpen(!open));
    menu.addEventListener('click', event => {
      if (event.target.closest('a[href]')) setOpen(false);
    });
    document.addEventListener('keydown', event => {
      if (!open) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
      } else if (event.key === 'Tab') {
        const targets = focusable();
        const first = targets[0];
        const last = targets[targets.length - 1];
        if (!first) return;
        if (event.shiftKey && (document.activeElement === first || !targets.includes(document.activeElement))) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !targets.includes(document.activeElement))) {
          event.preventDefault();
          first.focus();
        }
      }
    });
    document.addEventListener('focusin', event => {
      if (open && event.target !== toggle && !menu.contains(event.target)) {
        const target = focusable()[1] || toggle;
        target.focus({ preventScroll: true });
      }
    });
    mobile.addEventListener('change', () => {
      if (!mobile.matches && open) setOpen(false, false);
    });
  }

  function setupProgramTabs() {
    document.querySelectorAll('.program-tabs').forEach((tablist, groupIndex) => {
      const tabs = Array.from(tablist.querySelectorAll('.program-tab'));
      if (!tabs.length) return;
      tablist.setAttribute('role', 'tablist');

      function activate(tab, focus = false) {
        tabs.forEach((item, index) => {
          const selected = item === tab;
          const panelId = item.getAttribute('aria-controls') || `program-${item.dataset.program}`;
          const panel = document.getElementById(panelId);
          item.id ||= `program-tab-${groupIndex}-${index}`;
          item.setAttribute('role', 'tab');
          item.setAttribute('aria-controls', panelId);
          item.setAttribute('aria-selected', String(selected));
          item.tabIndex = selected ? 0 : -1;
          if (panel) {
            panel.hidden = !selected;
            panel.setAttribute('role', 'tabpanel');
            panel.setAttribute('aria-labelledby', item.id);
            panel.tabIndex = 0;
          }
        });
        if (focus) tab.focus();
      }

      activate(tabs.find(tab => tab.getAttribute('aria-selected') === 'true') || tabs[0]);
      tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => activate(tab));
        tab.addEventListener('keydown', event => {
          let next;
          if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
          else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
          else if (event.key === 'Home') next = 0;
          else if (event.key === 'End') next = tabs.length - 1;
          if (next !== undefined) {
            event.preventDefault();
            activate(tabs[next], true);
          }
        });
      });
    });
  }

  function setupJourney() {
    const journey = document.querySelector('.journey');
    if (!journey) return;
    const stage = journey.querySelector('.journey-stage');
    const boat = journey.querySelector('.journey-boat');
    const wake = journey.querySelector('.boat-wake');
    const progressBar = journey.querySelector('.journey-progress span');
    const description = document.getElementById('journey-description');
    const steps = Array.from(journey.querySelectorAll('.journey-step'));
    if (!stage || !boat || !steps.length) return;

    const descriptions = [
      'Routine checks, thoughtful upkeep, and a clear picture of your vessel’s condition.',
      'Maintenance, crew, and the finer details coordinated around your plans.',
      'A considered handover, with the details organized for your next day on the water.'
    ];
    let sectionTop = 0;
    let scrollDistance = 1;
    let boatHeight = 390;
    let frame = 0;
    let selectedStep = -1;
    let pendingTarget = null;

    if (description) description.setAttribute('aria-live', 'polite');

    function selectStep(index) {
      index = clamp(index, 0, descriptions.length - 1);
      if (index === selectedStep) return;
      selectedStep = index;
      steps.forEach((step, position) => {
        const active = Number(step.dataset.step ?? position) === index;
        step.classList.toggle('active', active);
        step.setAttribute('aria-pressed', String(active));
      });
      if (description) description.textContent = descriptions[index];
    }

    function measure() {
      sectionTop = journey.getBoundingClientRect().top + window.scrollY;
      scrollDistance = Math.max(1, journey.offsetHeight - stage.offsetHeight);
      boatHeight = boat.offsetHeight;
      schedule();
    }

    function render() {
      frame = 0;
      if (motionPreference.matches) {
        boat.style.removeProperty('transform');
        if (wake) wake.style.removeProperty('transform');
        if (progressBar) progressBar.style.width = `${Math.max(0, selectedStep) * 50}%`;
        return;
      }

      const progress = clamp((window.scrollY - sectionTop) / scrollDistance, 0, 1);
      const eased = progress * progress * (3 - 2 * progress);
      const x = -65 * Math.sin(progress * Math.PI * 0.8);
      const y = window.innerWidth <= 520 ? 30 - 40 * eased : window.innerWidth <= 800 ? 50 - 130 * eased : 90 - 210 * eased;
      const angle = 17 - 30 * progress;
      const translation = `translate3d(${x.toFixed(2)}px, ${y.toFixed(2)}px, 0)`;
      boat.style.transform = `translate(-50%, -50%) ${translation} rotate(${angle.toFixed(2)}deg)`;
      if (wake) wake.style.transform = `translate(-50%, 0) ${translation} rotate(${angle.toFixed(2)}deg) translateY(${(boatHeight * 0.46).toFixed(2)}px)`;
      if (progressBar) progressBar.style.width = `${(progress * 100).toFixed(2)}%`;

      if (pendingTarget && (Math.abs(window.scrollY - pendingTarget.top) < 3 || performance.now() > pendingTarget.expires)) pendingTarget = null;
      if (!pendingTarget) selectStep(Math.round(progress * 2));
    }

    function schedule() {
      if (!frame) frame = window.requestAnimationFrame(render);
    }

    steps.forEach((step, position) => {
      step.addEventListener('click', () => {
        const index = clamp(Number(step.dataset.step ?? position), 0, 2);
        selectStep(index);
        if (motionPreference.matches) {
          schedule();
          return;
        }
        const top = sectionTop + scrollDistance * index / 2;
        pendingTarget = { top, expires: performance.now() + 1800 };
        window.scrollTo({ top, behavior: 'smooth' });
        schedule();
      });
    });
    const cancelPending = () => { pendingTarget = null; };
    window.addEventListener('wheel', cancelPending, { passive: true });
    window.addEventListener('touchstart', cancelPending, { passive: true });
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', measure, { passive: true });
    motionPreference.addEventListener('change', () => {
      pendingTarget = null;
      measure();
    });
    if ('ResizeObserver' in window) new ResizeObserver(measure).observe(journey);
    if (boat instanceof HTMLImageElement && !boat.complete) boat.addEventListener('load', measure, { once: true });
    selectStep(0);
    measure();
  }

  function setupReveals() {
    const elements = Array.from(document.querySelectorAll('.reveal'));
    if (!elements.length || motionPreference.matches || !('IntersectionObserver' in window)) return;
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -25px 0px' });
    document.documentElement.classList.add('js-motion');
    elements.forEach(element => observer.observe(element));
    motionPreference.addEventListener('change', event => {
      if (event.matches) {
        observer.disconnect();
        document.documentElement.classList.remove('js-motion');
        elements.forEach(element => element.classList.add('visible'));
      }
    });
  }

  function setupInquiry() {
    const form = document.getElementById('inquiry-form');
    if (!form) return;
    const result = document.getElementById('form-result');
    const download = document.getElementById('download-inquiry');
    const copy = document.getElementById('copy-inquiry');
    let brief = '';
    let downloadUrl = '';
    let copyStatus;

    const interest = form.elements.namedItem('interest');
    const requestedInterest = new URLSearchParams(window.location.search).get('interest');
    const normalize = value => value.toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]/g, '');
    const requiredText = ['name', 'vessel'].map(name => form.elements.namedItem(name)).filter(Boolean);
    requiredText.forEach(field => field.addEventListener('input', () => field.setCustomValidity('')));
    if (interest instanceof HTMLSelectElement && requestedInterest) {
      const requested = normalize(requestedInterest);
      const option = Array.from(interest.options).find(item => item.value && (normalize(item.value) === requested || normalize(item.textContent) === requested));
      if (option) interest.value = option.value;
    }

    function fieldValue(name) {
      const field = form.elements.namedItem(name);
      if (!field) return 'Not provided';
      const value = String(field.value || '').trim();
      if (!value) return 'Not provided';
      if (field instanceof HTMLSelectElement) return (field.selectedOptions[0]?.textContent || value).trim();
      return value;
    }

    form.addEventListener('submit', event => {
      event.preventDefault();
      requiredText.forEach(field => {
        field.setCustomValidity(field.value.trim() ? '' : 'Please enter this information.');
      });
      if (!form.reportValidity()) return;
      const fields = [
        ['Name', 'name'], ['Email', 'email'], ['Phone', 'phone'],
        ['Vessel', 'vessel'], ['Vessel length', 'length'], ['Vessel location', 'location'],
        ['Interested in', 'interest'], ['Preferred timing', 'timing']
      ];
      brief = [
        'LAS OLAS YACHT MANAGEMENT', 'INQUIRY BRIEF', '',
        `Prepared: ${new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })}`,
        'Prepared in your browser. No inquiry has been sent.', '',
        ...fields.map(([label, name]) => `${label}: ${fieldValue(name)}`),
        '', 'Message:', fieldValue('message'), ''
      ].join('\n');

      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
      downloadUrl = URL.createObjectURL(new Blob([brief], { type: 'text/plain;charset=utf-8' }));
      if (download instanceof HTMLAnchorElement) {
        download.href = downloadUrl;
        download.download = 'las-olas-yacht-inquiry.txt';
      }
      if (copyStatus) copyStatus.textContent = '';
      if (result) {
        result.hidden = false;
        result.tabIndex = -1;
        result.focus({ preventScroll: true });
        result.scrollIntoView({ behavior: motionPreference.matches ? 'auto' : 'smooth', block: 'nearest' });
      }
    });

    if (download && !(download instanceof HTMLAnchorElement)) {
      download.addEventListener('click', event => {
        event.preventDefault();
        if (!downloadUrl) return;
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = 'las-olas-yacht-inquiry.txt';
        document.body.appendChild(link);
        link.click();
        link.remove();
      });
    }

    function fallbackCopy() {
      const temporary = document.createElement('textarea');
      temporary.value = brief;
      temporary.setAttribute('readonly', '');
      temporary.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
      document.body.appendChild(temporary);
      temporary.select();
      let copied = false;
      try { copied = document.execCommand('copy'); } catch (_) { /* The download remains available. */ }
      temporary.remove();
      copy?.focus({ preventScroll: true });
      return copied;
    }

    if (copy) {
      copy.addEventListener('click', async event => {
        event.preventDefault();
        if (!brief) return;
        let copied = false;
        try {
          if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(brief);
            copied = true;
          } else copied = fallbackCopy();
        } catch (_) { copied = fallbackCopy(); }
        if (!copyStatus) {
          copyStatus = document.createElement('p');
          copyStatus.setAttribute('role', 'status');
          copyStatus.setAttribute('aria-live', 'polite');
          (result || copy.parentElement).appendChild(copyStatus);
        }
        copyStatus.textContent = copied ? 'Brief copied to your clipboard.' : 'Copy is unavailable in this browser. Use Download brief to save your inquiry.';
      });
    }
    const submit = document.getElementById('inquiry-submit');
    if (submit instanceof HTMLButtonElement) submit.disabled = false;
  }

  function initialize() {
    setupStickyHeader();
    setupMenu();
    setupProgramTabs();
    setupJourney();
    setupReveals();
    setupInquiry();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
