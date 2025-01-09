import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import logging
import re
import time
from urllib.parse import urlparse, urljoin, urlunparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
from PIL import Image
import io
import os


class AIToolsCrawler:
    def __init__(self, output_file='ai_tools.json'):
        """初始化爬虫"""
        self.config = {
            'max_retries': 5,
            'retry_delay': 10,
            'scroll_count': 1,
            'min_request_interval': 3.0,
            'timeout': 45,
            'page_load_timeout': 90,
            'screenshots_dir': 'screenshots'  # 添加截图保存目录
        }

        # 确保截图目录存在
        os.makedirs(self.config['screenshots_dir'], exist_ok=True)

        self.output_file = output_file
        self.tools_data = []
        self.setup_logging()
        self.setup_selenium()
        self.last_request_time = 0

    def setup_logging(self):
        """配置日志系统"""
        logging.basicConfig(
            filename='crawler.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            encoding='utf-8'
        )
        # 同时输出到控制台
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(console_handler)

    def setup_selenium(self):
        """配置Selenium无头浏览器"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--enable-javascript')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        # 添加新的配置项
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.set_page_load_timeout(self.config['page_load_timeout'])
        self.driver.set_script_timeout(self.config['page_load_timeout'])

    def scroll_page(self):
        """通过滚动加载更多内容"""
        SCROLL_PAUSE_TIME = 2
        max_attempts = self.config['scroll_count']
        attempts = 0
        last_height = self.driver.execute_script("return document.body.scrollHeight")

        while attempts < max_attempts:
            try:
                # 滚动到页面底部
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(SCROLL_PAUSE_TIME)  # 等待页面加载

                # 计算新的滚动高度并与上一次的滚动高度进行比较
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                
                # 获取当前加载的卡片数量
                cards = self.driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="MostLovedCardDesktop"]')
                logging.info(f"已加载 {len(cards)} 个产品")
                
                # 如果高度没有变化，说明已经到底部
                if new_height == last_height:
                    logging.info("已到达页面底部")
                    break
                    
                last_height = new_height
                attempts += 1
                
            except Exception as e:
                logging.warning(f"滚动加载更多内容时出错: {str(e)}")
                break
        
        logging.info(f"完成滚动加载操作，共滚动 {attempts} 次")

    def get_real_url(self, product_url, original_url):
        """通过产品详情页获取真实URL，并确保能够返回原始页面"""
        try:
            logging.info(f"访问产品详情页: {product_url}")
            
            # 保存当前窗口句柄
            original_window = self.driver.current_window_handle
            
            # 创建新标签页
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            
            try:
                # 在新标签页中加载产品详情页
                self.driver.get(product_url)
                wait = WebDriverWait(self.driver, self.config['timeout'])
                
                # 尝试多个可能的选择器来定位 Visit Website 按钮
                website_link = None
                selectors = [
                    "//a[contains(text(), 'Visit website')]",
                    "//a[contains(@class, 'styles_websiteButton')]",
                    "//a[contains(@data-test, 'website-link')]",
                    "//a[contains(@class, 'styles_button') and contains(@class, 'styles_website')]"
                ]
                
                real_url = None
                for selector in selectors:
                    try:
                        website_link = wait.until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        if website_link:
                            real_url = website_link.get_attribute('href')
                            if real_url:
                                logging.info(f"成功获取真实URL: {real_url}")
                                break
                    except Exception as e:
                        logging.debug(f"使用选择器 {selector} 查找失败: {str(e)}")
                        continue
                
                return real_url
                
            finally:
                # 关闭当前标签页并切回原始标签页
                self.driver.close()
                self.driver.switch_to.window(original_window)
                
        except Exception as e:
            logging.error(f"获取真实URL时出错: {str(e)}")
            # 确保返回原始窗口
            try:
                self.driver.switch_to.window(original_window)
            except:
                pass
            return None

    def clear_browser_data(self):
        """清理浏览器数据"""
        try:
            # 只清理 cookies
            self.driver.delete_all_cookies()
            logging.info("已清理cookies")
            
            # 只在正常页面（非data: URL）时清理存储
            current_url = self.driver.current_url
            if not current_url.startswith('data:'):
                try:
                    self.driver.execute_script("window.localStorage.clear();")
                    self.driver.execute_script("window.sessionStorage.clear();")
                    logging.info("已清理localStorage和sessionStorage")
                except Exception as storage_error:
                    logging.debug(f"清理存储时出错（非致命）: {str(storage_error)}")
            
        except Exception as e:
            logging.warning(f"清理浏览器数据时出错: {str(e)}")
            # 继续执行，不中断程序

    def take_website_screenshot(self, url, tool_name):
        """
        访问网站并保存截图
        
        Args:
            url: 网站URL
            tool_name: 工具名称（用于生成文件名）
        
        Returns:
            str: 截图文件路径，如果失败则返回None
        """
        try:
            # 保存当前窗口句柄
            original_window = self.driver.current_window_handle
            
            # 创建新标签页
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            
            try:
                # 设置窗口大小
                self.driver.set_window_size(1920, 1080)
                
                # 访问网站
                self.driver.get(url)
                
                # 等待页面加载
                wait = WebDriverWait(self.driver, self.config['timeout'])
                wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
                
                # 额外等待以确保动态内容加载
                time.sleep(3)
                
                # 生成文件名（使用时间戳避免重名）
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = re.sub(r'[^\w\-_]', '_', tool_name)
                filename = f"{safe_name}_{timestamp}.png"
                filepath = os.path.join(self.config['screenshots_dir'], filename)
                
                # 保存截图
                self.driver.save_screenshot(filepath)
                
                # 使用Pillow优化图片
                with Image.open(filepath) as img:
                    # 压缩图片
                    img.save(filepath, 'PNG', optimize=True, quality=85)
                
                logging.info(f"成功保存截图: {filepath}")
                return filename
                
            finally:
                # 关闭新标签页并返回原始标签页
                self.driver.close()
                self.driver.switch_to.window(original_window)
                
        except Exception as e:
            logging.error(f"截图失败 {url}: {str(e)}")
            return None

    def crawl_producthunt(self):
        """爬取ProductHunt上的AI工具"""
        url = "https://www.producthunt.com/topics/artificial-intelligence"
        try:
            logging.info(f"开始访问URL: {url}")
            
            # 改进的重试机制
            for attempt in range(self.config['max_retries']):
                try:
                    # 先访问主页
                    self.driver.get("https://www.producthunt.com")
                    time.sleep(2)
                    
                    # 清理浏览器数据（在加载正常页面后）
                    self.clear_browser_data()
                    
                    # 然后访问目标页面
                    self.driver.get(url)
                    
                    # 等待页面加载完成
                    wait = WebDriverWait(self.driver, self.config['timeout'])
                    wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
                    
                    # 等待并点击 Top Products 按钮
                    top_products_selectors = [
                        "//button[contains(text(), 'Top Products')]",
                        "//button[contains(@class, 'styles_inactiveTab') and contains(text(), 'Top Products')]",
                        "//div[contains(@class, 'flex-row')]//button[contains(text(), 'Top Products')]"
                    ]
                    
                    button_clicked = False
                    for selector in top_products_selectors:
                        try:
                            button = wait.until(
                                EC.element_to_be_clickable((By.XPATH, selector))
                            )
                            # 截图记录点击前状态
                            self.driver.save_screenshot(f"before_click_{attempt}.png")
                            
                            # 使用JavaScript点击按钮
                            self.driver.execute_script("arguments[0].click();", button)
                            logging.info(f"成功点击Top Products按钮，使用选择器: {selector}")
                            button_clicked = True
                            
                            # 等待页面更新
                            time.sleep(3)
                            break
                        except Exception as click_error:
                            logging.debug(f"使用选择器 {selector} 点击失败: {str(click_error)}")
                            continue
                    
                    if not button_clicked:
                        raise Exception("未能找到或点击Top Products按钮")
                    
                    # 保存点击后的截图
                    self.driver.save_screenshot(f"after_click_{attempt}.png")
                    
                    # 验证页面内容更新
                    wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, '[data-sentry-component="ProductItem"]')) > 0)
                    
                    logging.info("页面加载和切换成功")
                    break
                    
                except Exception as e:
                    logging.warning(f"第 {attempt + 1} 次加载失败: {str(e)}")
                    if attempt == self.config['max_retries'] - 1:
                        raise Exception(f"在 {self.config['max_retries']} 次尝试后仍无法加载页面")
                    
                    # 诊断信息
                    try:
                        logging.info(f"当前页面标题: {self.driver.title}")
                        logging.info(f"当前URL: {self.driver.current_url}")
                        logging.info(f"页面源码长度: {len(self.driver.page_source)}")
                        self.driver.save_screenshot(f"error_screenshot_{attempt}.png")
                        
                        # 保存页面源码以便分析
                        with open(f'page_source_{attempt}.html', 'w', encoding='utf-8') as f:
                            f.write(self.driver.page_source)
                    except Exception as debug_error:
                        logging.error(f"保存调试信息时出错: {str(debug_error)}")
                    
                    time.sleep(self.config['retry_delay'] * (attempt + 1))
            
            # 保存页面源码以便调试
            with open('page_source.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            
            # 截图保存当前页面状态
            self.driver.save_screenshot("initial_page_load.png")
            
            logging.info("主页面加载成功，准备处理内容")
            
            # 开始滚动加载更多内容
            self.scroll_page()

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            product_cards = soup.find_all('div', {'data-sentry-component': 'ProductItem'})
            logging.info(f"滚动加载后总共找到 {len(product_cards)} 个产品卡片")

            for card in product_cards:
                try:
                    # 增加显式等待
                    wait = WebDriverWait(self.driver, self.config['timeout'])
                    
                    # 提取产品名称和链接
                    name_elem = card.find('div', {'data-test': 'product-item-name'})
                    if not name_elem:
                        logging.warning("未找到产品名称元素，跳过该卡片")
                        continue

                    # 提取产品名称（去掉描述部分）
                    name_text = name_elem.get_text(strip=True)
                    name = name_text.split('—')[0].strip()
                    description = name_text.split('—')[1].strip() if len(name_text.split('—')) > 1 else ''
                    
                    # 获取产品链接并访问产品详情页
                    link_elem = card.find('a', href=True)
                    if link_elem:
                        product_base_url = urljoin("https://www.producthunt.com", link_elem.get('href', ''))
                        # 确保URL指向产品主页而不是shoutouts页面
                        product_url = product_base_url.split('/shoutouts')[0]
                        
                        # 获取真实URL
                        real_url = self.get_real_url(product_url, url)
                        if not real_url:
                            logging.warning(f"跳过产品 {name}：无法获取真实URL")
                            continue

                        # 清理URL
                        parsed_url = urlparse(real_url)
                        clean_url = urlunparse((
                            parsed_url.scheme,
                            parsed_url.netloc,
                            parsed_url.path,
                            '',
                            '',
                            ''
                        ))
                    
                    # 获取缩略图
                    thumbnail_elem = card.find('img', {'loading': 'lazy'})
                    thumbnail = thumbnail_elem.get('src') if thumbnail_elem else ''
                    
                    # 获取标签
                    tags = []
                    tag_links = card.find_all('a', {'class': 'text-12'})
                    for tag_link in tag_links:
                        tag_text = tag_link.get_text(strip=True)
                        if tag_text:
                            tags.append(tag_text)
                    
                    # 获取关注者数量
                    followers_elem = card.find('div', {'class': 'styles_followersCount__Auv5S'})
                    followers_text = followers_elem.get_text(strip=True) if followers_elem else '0'
                    followers = int(''.join(filter(str.isdigit, followers_text)))

                    # 获取网站截图
                    screenshot_filename = self.take_website_screenshot(clean_url, name)
                    
                    tool_data = {
                        'name': name,
                        'url': clean_url,
                        'description': description,
                        'thumbnail': thumbnail,
                        'followers': followers,
                        'tags': tags,
                        'category': 'AI',
                        'source': 'ProductHunt',
                        'screenshot': screenshot_filename,
                        'crawled_at': datetime.now().isoformat()
                    }

                    self.tools_data.append(tool_data)
                    logging.info(f"成功处理产品: {name}, 标签: {tags}")

                    # 确保主页面正常显示
                    retry_count = 0
                    while retry_count < self.config['max_retries']:
                        try:
                            # 检查页面是否仍然可用
                            self.driver.find_element(By.CSS_SELECTOR, '[data-sentry-component="ProductItem"]')
                            break
                        except Exception as e:
                            retry_count += 1
                            if retry_count == self.config['max_retries']:
                                logging.error("主页面状态异常，尝试重新加载")
                                self.driver.get(url)
                                wait.until(EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, '[data-sentry-component="ProductItem"]')
                                ))
                            time.sleep(self.config['retry_delay'])

                    # 随机化等待时间
                    wait_time = self.config['min_request_interval'] + random.uniform(1, 3)
                    time.sleep(wait_time)

                except Exception as e:
                    logging.error(f"处理产品卡片时出错: {str(e)}", exc_info=True)
                    # 尝试恢复到主页面
                    try:
                        self.driver.get(url)
                        time.sleep(self.config['retry_delay'])
                    except:
                        logging.error("无法恢复到主页面，退出循环")
                        break

        except Exception as e:
            logging.error(f"爬取ProductHunt时出错: {str(e)}\n错误类型: {type(e).__name__}\n错误详情: {e.__dict__}")
            # 保存错误时的页面源码和截图
            try:
                with open('error_page_source.html', 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                self.driver.save_screenshot("error_page.png")
            except:
                pass
            raise

    def save_data(self):
        """保存数据到JSON文件"""
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(self.tools_data, f, ensure_ascii=False, indent=2)
            logging.info(f"Saved {len(self.tools_data)} tools to {self.output_file}")
        except Exception as e:
            logging.error(f"Error saving data: {str(e)}")

    def run(self):
        """运行爬虫主程序"""
        try:
            logging.info("Starting crawler run")

            # 爬取数据
            self.crawl_producthunt()

            # 保存数据
            self.save_data()

            logging.info("Completed crawler run")

        except Exception as e:
            logging.error(f"Error in main crawler run: {str(e)}")

        finally:
            # 清理资源
            if hasattr(self, 'driver'):
                self.driver.quit()


if __name__ == "__main__":
    try:
        crawler = AIToolsCrawler()
        crawler.run()
    except Exception as e:
        logging.error(f"Critical error in main: {str(e)}")