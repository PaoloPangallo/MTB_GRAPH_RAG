import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Set viewport size to ensure high resolution and fit the diagram
        await page.set_viewport_size({"width": 2500, "height": 2000})
        
        # Resolve absolute path to file
        file_path = os.path.abspath(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\data_expl\snapshot\pipeline_mtb_v3.html")
        file_url = f"file:///{file_path.replace(os.sep, '/')}"
        print(f"Loading URL: {file_url}")
        
        # Open the file
        await page.goto(file_url)
        
        # Wait for mermaid to complete rendering. 
        # When mermaid renders successfully, it adds a data-processed="true" attribute, or creates an SVG inside the .mermaid div.
        # Let's wait for the svg to be present inside .mermaid.
        await page.wait_for_selector(".mermaid svg")
        
        # Add a small delay to ensure rendering and animations are completed
        await asyncio.sleep(1)
        
        # Get the element handle
        element = await page.query_selector(".mermaid")
        if element:
            # Take screenshot with transparent background
            await element.screenshot(path=r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\data_expl\snapshot\pipeline_mtb_v3.png", omit_background=True)
            print("Screenshot saved to pipeline_mtb_v3.png successfully!")
        else:
            print("Element .mermaid not found!")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
