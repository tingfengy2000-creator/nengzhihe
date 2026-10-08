import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    svg=open('framework.svg').read()
    html=f'<html><head><meta charset="utf-8"><style>html,body{{margin:0;background:#fff}}</style></head><body>{svg}</body></html>'
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={'width':1800,'height':1080}, device_scale_factor=float(sys.argv[1]) if len(sys.argv)>1 else 1)
        await pg.set_content(html); await pg.wait_for_timeout(300)
        await pg.screenshot(path=sys.argv[2] if len(sys.argv)>2 else 'preview.png', clip={'x':0,'y':0,'width':1800,'height':1080})
        if len(sys.argv)>3:
            await pg.pdf(path=sys.argv[3], width='1800px', height='1080px', print_background=True, page_ranges='1')
        await b.close()
asyncio.run(main())
