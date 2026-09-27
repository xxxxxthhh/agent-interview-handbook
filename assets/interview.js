/* Interview Bench：交卷台、计时器、逐层追问、打印展开。
   渐进增强：没有 JS 时，<details> 仍可逐个展开，textarea 仍可书写，计时与导出按钮保持隐藏。
   草稿默认不写入浏览器；只有读者勾选「保存到此浏览器」才写 localStorage，键带 schema 版本。 */
(function () {
  var PREFIX = 'aih:';
  var SCHEMA = 'v1';

  function store(fn) { try { return fn(window.localStorage); } catch (e) { return null; } }

  /* ---------- 计时器 ---------- */
  function initTimer(el) {
    var total = parseInt(el.getAttribute('data-seconds'), 10);
    var read = el.querySelector('.t-read');
    var bar = el.querySelector('.t-bar span');
    var btn = el.querySelector('[data-act="toggle"]');
    var left = total, tick = null, endAt = 0;

    function fmt(s) {
      var m = Math.floor(s / 60), r = s % 60;
      return (m < 10 ? '0' : '') + m + ':' + (r < 10 ? '0' : '') + r;
    }
    function paint() {
      read.textContent = fmt(left);
      bar.style.width = ((total - left) / total * 100) + '%';
      el.classList.toggle('warn', left <= total * 0.2 && left > 0);
      el.classList.toggle('done', left === 0);
    }
    function stop() { clearInterval(tick); tick = null; btn.textContent = left === 0 ? '重来' : '继续'; }
    function step() {
      left = Math.max(0, Math.round((endAt - Date.now()) / 1000));
      paint();
      if (left === 0) stop();
    }
    btn.addEventListener('click', function () {
      if (tick) { stop(); return; }
      if (left === 0) left = total;
      endAt = Date.now() + left * 1000;
      tick = setInterval(step, 250);
      btn.textContent = '暂停';
      paint();
    });
    el.querySelector('[data-act="reset"]').addEventListener('click', function () {
      clearInterval(tick); tick = null; left = total; btn.textContent = '开始'; paint();
    });
    el.hidden = false;
    paint();
  }

  /* ---------- 交卷台 ---------- */
  function initBench(bench) {
    var unit = bench.getAttribute('data-bench');
    var key = PREFIX + unit + ':submission:' + SCHEMA;
    var ta = bench.querySelector('[data-submission]');
    var ctl = bench.querySelector('.bench-ctl');
    var persist = bench.querySelector('[data-act="persist"]');

    var saved = store(function (ls) { return ls.getItem(key); });
    if (saved) { ta.value = saved; persist.checked = true; }

    function save() { if (persist.checked) store(function (ls) { ls.setItem(key, ta.value); }); }
    ta.addEventListener('input', save);
    persist.addEventListener('change', function () {
      if (persist.checked) save();
      else store(function (ls) { ls.removeItem(key); });
    });

    bench.querySelector('[data-act="export"]').addEventListener('click', function () {
      var d = new Date();
      var stamp = d.getFullYear() + String(d.getMonth() + 1).padStart(2, '0') + String(d.getDate()).padStart(2, '0');
      var text = '# ' + unit + ' 交卷 · ' + d.toISOString().slice(0, 16).replace('T', ' ') + '\n\n' + ta.value + '\n';
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }));
      a.download = unit + '-submission-' + stamp + '.md';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    });

    // 清除操作用「再点一次确认」，不弹浏览器对话框
    function confirmable(btn, run) {
      var label = btn.textContent, armed = null;
      btn.addEventListener('click', function () {
        if (!armed) {
          btn.textContent = '再点一次确认';
          armed = setTimeout(function () { btn.textContent = label; armed = null; }, 3000);
          return;
        }
        clearTimeout(armed); armed = null; btn.textContent = label; run();
      });
    }
    confirmable(bench.querySelector('[data-act="clear"]'), function () {
      ta.value = ''; store(function (ls) { ls.removeItem(key); }); persist.checked = false;
    });
    confirmable(bench.querySelector('[data-act="clear-all"]'), function () {
      store(function (ls) {
        for (var i = ls.length - 1; i >= 0; i--) { var k = ls.key(i); if (k && k.indexOf(PREFIX) === 0) ls.removeItem(k); }
      });
      ta.value = ''; persist.checked = false;
    });
    ctl.hidden = false;
  }

  /* ---------- 逐层追问 ---------- */
  function initFollowups(list) {
    var items = list.querySelectorAll(':scope > li');
    var btn = list.parentNode.querySelector('[data-act="next-layer"]');
    if (items.length < 2 || !btn) return;
    for (var i = 1; i < items.length; i++) items[i].classList.add('locked');
    btn.hidden = false;
    btn.addEventListener('click', function () {
      var next = list.querySelector(':scope > li.locked');
      if (next) {
        next.classList.remove('locked');
        var q = next.querySelector('.fq');
        if (q) { q.setAttribute('tabindex', '-1'); q.focus({ preventScroll: false }); }
      }
      if (!list.querySelector(':scope > li.locked')) btn.hidden = true;
    });
  }

  /* ---------- 打印：展开全部 ---------- */
  var reopened = [];
  window.addEventListener('beforeprint', function () {
    reopened = [];
    document.querySelectorAll('details.reveal:not([open])').forEach(function (d) { d.open = true; reopened.push(d); });
  });
  window.addEventListener('afterprint', function () {
    reopened.forEach(function (d) { d.open = false; });
  });

  function init() {
    document.querySelectorAll('[data-timer]').forEach(initTimer);
    document.querySelectorAll('[data-bench]').forEach(initBench);
    document.querySelectorAll('[data-followups]').forEach(initFollowups);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
