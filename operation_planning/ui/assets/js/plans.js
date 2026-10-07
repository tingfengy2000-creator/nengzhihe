/* 能见度 · 我的方案（第 1 批外壳占位，后续批次实现） */
export function show(el) {
  if (el.dataset.ready) return;
  el.dataset.ready = '1';
  el.innerHTML = '<section class="page-head"><div class="container"><p class="kicker">能见度</p><h1 class="h2">我的方案</h1><p class="sub">外壳已就绪，本页内容在后续批次实现。</p></div></section>';
}
