/* 能见度 · 示例（第 6 批完整实现；本批支持 #/samples/<case_id> 直接打开示例结果） */
import * as tool from './tool.js';
export function show(el, args = []) {
  if (args[0]) { tool.openSample(args[0], 3); return; }
  if (el.dataset.ready) return;
  el.dataset.ready = '1';
  el.innerHTML = '<section class="page-head"><div class="container"><p class="kicker">示例</p><h1 class="h2">示例</h1><p class="sub">示例列表在后续批次实现；可从首页三档卡片打开示例。</p></div></section>';
}
