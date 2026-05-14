// @ts-check

const { createHash } = require("node:crypto");
const { createReadStream } = require("node:fs");
const fs = require("node:fs/promises");
const path = require("node:path");
const readline = require("node:readline");
const readlinePromises = require("node:readline/promises");
const { stdin, stdout } = require("node:process");
const { createRequire } = require("node:module");

const REQUEST_DELAY_MS = 500;
const POSTS_PER_PAGE = 200;
const PROGRESS_BAR_WIDTH = 20;
/**
 * @typedef {{
 *   url: string,
 *   output: string,
 *   timeoutMs: number,
 *   headless: boolean,
 *   profileDir: string,
 *   playwrightPackageDir: string,
 * }} BrowserScriptArgs
 */

/**
 * @typedef {{
 *   url: string,
 *   output: string,
 *   timeoutMs: number,
 *   headless: boolean,
 * }} RuntimeConfig
 */

/**
 * @typedef {{
 *   totalPages: number,
 *   totalPosts: number,
 *   currentPageNumber: number,
 *   processedPosts: number,
 *   savedCount: number,
 *   skippedCount: number,
 *   failedCount: number,
 * }} ProgressState
 */

/**
 * @typedef {{
 *   md5?: unknown,
 * }} DanbooruMediaAssetLike
 */

/**
 * @typedef {{
 *   id?: unknown,
 *   md5?: unknown,
 *   media_asset?: DanbooruMediaAssetLike | null,
 * }} DanbooruPostLike
 */

/** @type {ProgressState | null} */
let progressState = null;
/** @type {RuntimeConfig | null} */
let runtimeConfig = null;
/** @type {Set<string> | null} */
let existingFileHashes = null;

/**
 * @param {string} value
 * @returns {number}
 */
function parseTimeoutMs(value) {
  const timeoutSeconds = Number(value);
  if (!Number.isFinite(timeoutSeconds) || timeoutSeconds < 0) {
    throw new Error("Invalid --timeout value. Use a number greater than or equal to 0.");
  }

  if (timeoutSeconds === 0) {
    return 0;
  }

  return timeoutSeconds * 1000;
}

/**
 * @param {string[]} argv
 * @returns {BrowserScriptArgs}
 */
function parseArgs(argv) {
  /** @type {BrowserScriptArgs} */
  const args = {
    url: "",
    output: "",
    timeoutMs: 30000,
    headless: false,
    profileDir: "",
    playwrightPackageDir: "",
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--url") {
      args.url = argv[index + 1] ?? "";
      index += 1;
    } else if (arg === "--output") {
      args.output = argv[index + 1] ?? "";
      index += 1;
    } else if (arg === "--timeout") {
      args.timeoutMs = parseTimeoutMs(argv[index + 1] ?? "30");
      index += 1;
    } else if (arg === "--profile-dir") {
      args.profileDir = argv[index + 1] ?? "";
      index += 1;
    } else if (arg === "--playwright-package-dir") {
      args.playwrightPackageDir = argv[index + 1] ?? "";
      index += 1;
    } else if (arg === "--headless") {
      args.headless = true;
    }
  }

  if (!args.url || !args.output || !args.profileDir || !args.playwrightPackageDir) {
    throw new Error("Missing required browser script arguments.");
  }

  return args;
}

/**
 * @returns {RuntimeConfig}
 */
function getRuntimeConfig() {
  if (runtimeConfig === null) {
    throw new Error("Runtime config has not been initialized.");
  }

  return runtimeConfig;
}

/**
 * @returns {Set<string>}
 */
function getExistingFileHashes() {
  if (existingFileHashes === null) {
    throw new Error("Existing file hashes have not been initialized.");
  }

  return existingFileHashes;
}

/**
 * @param {BrowserScriptArgs} args
 * @returns {void}
 */
function initializeRuntimeConfig(args) {
  runtimeConfig = {
    url: args.url,
    output: args.output,
    timeoutMs: args.timeoutMs,
    headless: args.headless,
  };
}

/**
 * @returns {URLSearchParams}
 */
function buildApiQueryParams() {
  const { url } = getRuntimeConfig();
  const parsed = new URL(url);
  const queryParams = new URLSearchParams(parsed.search);
  const cleaned = new URLSearchParams();

  for (const [key, value] of queryParams.entries()) {
    const normalizedValue = key === "tags" ? value.trim().replace(/\s+/g, " ") : value.trim();
    if (normalizedValue) {
      cleaned.append(key, normalizedValue);
    }
  }

  return cleaned;
}

/**
 * @param {number} page
 * @returns {string}
 * API查询：baseurl/posts.json?tags=...&page=...&limit=...
 */
function buildPostsApiUrl(page) {
  const { url } = getRuntimeConfig();
  const parsed = new URL(url);
  const queryParams = buildApiQueryParams();
  queryParams.delete("z");
  queryParams.set("page", String(page));
  queryParams.set("limit", String(POSTS_PER_PAGE));
  parsed.pathname = "/posts.json";
  parsed.search = queryParams.toString();
  parsed.hash = "";
  return parsed.toString();
}

/**
 * @returns {string}
 * API查询：baseurl/counts/posts.json?tags=...
 */
function buildCountsApiUrl() {
  const { url } = getRuntimeConfig();
  const parsed = new URL(url);
  const queryParams = buildApiQueryParams();
  queryParams.delete("z");
  queryParams.delete("page");
  queryParams.delete("limit");
  parsed.pathname = "/counts/posts.json";
  parsed.search = queryParams.toString();
  parsed.hash = "";
  return parsed.toString();
}

/**
 * @param {unknown} post
 * @returns {string | null}
 */
function getPostId(post) {
  if (!post || typeof post !== "object") {
    return null;
  }

  const postLike = /** @type {DanbooruPostLike} */ (post);
  const postId = postLike.id;
  if (typeof postId === "number") {
    return String(postId);
  }

  if (typeof postId === "string" && /^\d+$/.test(postId)) {
    return postId;
  }

  return null;
}

/**
 * @param {unknown} post
 * @returns {string | null}
 */
function getPostHash(post) {
  if (!post || typeof post !== "object") {
    return null;
  }

  const postLike = /** @type {DanbooruPostLike} */ (post);
  const candidates = [postLike.md5, postLike.media_asset?.md5];

  for (const candidate of candidates) {
    if (typeof candidate === "string" && /^[a-f0-9]{32}$/i.test(candidate)) {
      return candidate.toLowerCase();
    }
  }

  return null;
}

/**
 * @param {string} postId
 * @returns {string}
 */
function buildPostUrl(postId) {
  const { url } = getRuntimeConfig();
  return new URL(`/posts/${postId}`, url).toString();
}

/**
 * @param {string} downloadUrl
 * @param {string | null} downloadAttribute
 * @returns {string}
 */
function resolveDownloadFilename(downloadUrl, downloadAttribute) {
  if (typeof downloadAttribute === "string") {
    const candidate = path.posix.basename(downloadAttribute.trim());
    if (candidate) {
      return candidate;
    }
  }

  const parsed = new URL(downloadUrl);
  const filename = path.posix.basename(parsed.pathname);
  if (!filename) {
    throw new Error(`Invalid file URL: ${downloadUrl}`);
  }
  return filename;
}

/**
 * @param {string} filename
 * @returns {string | null}
 */
function extractEmbeddedHash(filename) {
  const stem = path.parse(filename).name;
  const separatorIndex = stem.lastIndexOf(" - ");
  if (separatorIndex < 0) {
    return null;
  }

  const candidate = stem.slice(separatorIndex + 3).trim();
  if (!/^[a-f0-9]{32}$/i.test(candidate)) {
    return null;
  }

  return candidate.toLowerCase();
}

/**
 * @param {string} outputDir
 * @returns {Promise<void>}
 */
async function initializeExistingFileHashes(outputDir) {
  const hashes = new Set();
  const entries = await fs.readdir(outputDir, { withFileTypes: true });

  for (const entry of entries) {
    if (!entry.isFile()) {
      continue;
    }

    const filePath = path.join(outputDir, entry.name);
    const hash = extractEmbeddedHash(entry.name) ?? (await calculateFileMd5(filePath));
    if (hash) {
      hashes.add(hash);
    }
  }

  existingFileHashes = hashes;
}

/**
 * @param {string} filePath
 * @returns {Promise<void>}
 */
async function rememberExistingFileHashes(filePath) {
  const hashes = getExistingFileHashes();
  const hash = extractEmbeddedHash(path.basename(filePath)) ?? (await calculateFileMd5(filePath));
  if (hash) {
    hashes.add(hash);
  }
}

/**
 * @param {string} filePath
 * @returns {Promise<string | null>}
 */
async function calculateFileMd5(filePath) {
  return await new Promise((resolve, reject) => {
    const hasher = createHash("md5");
    const stream = createReadStream(filePath);

    stream.on("error", reject);
    stream.on("data", (chunk) => {
      hasher.update(chunk);
    });
    stream.on("end", () => {
      resolve(hasher.digest("hex"));
    });
  });
}

/**
 * @param {number} ms
 * @returns {Promise<void>}
 */
async function delay(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * @param {string} targetPath
 * @returns {Promise<boolean>}
 */
async function fileExists(targetPath) {
  try {
    await fs.access(targetPath);
    return true;
  } catch {
    return false;
  }
}

/**
 * @param {unknown} error
 * @returns {string}
 */
function getErrorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

/**
 * @param {import("playwright").Page} page
 * @returns {Promise<boolean>}
 */
async function isChallengePage(page) {
  const title = await page.title();
  if (title.includes("Just a moment")) {
    return true;
  }

  const bodyText = await page.locator("body").innerText().catch(() => "");
  return bodyText.includes("Enable JavaScript and cookies to continue");
}

/**
 * @param {import("playwright").Page} page
 * @returns {Promise<void>}
 */
async function waitForChallengeClear(page) {
  const { headless } = getRuntimeConfig();
  if (!(await isChallengePage(page))) {
    return;
  }

  if (headless) {
    throw new Error("Cloudflare challenge detected in headless mode. Rerun without --headless and pass the challenge in the browser.");
  }

  console.log("Cloudflare challenge detected. Complete it in the opened browser, then press Enter here to continue.");
  const rl = readlinePromises.createInterface({ input: stdin, output: stdout });
  try {
    await rl.question("");
  } finally {
    rl.close();
  }

  await page.waitForLoadState("domcontentloaded", { timeout: 10000 }).catch(() => {});
  if (await isChallengePage(page)) {
    throw new Error("Cloudflare challenge is still active after manual confirmation.");
  }
}

/**
 * @param {number} current
 * @param {number} total
 * @returns {string}
 */
function formatProgressBar(current, total) {
  const safeTotal = Math.max(total, 1);
  const clampedCurrent = Math.min(Math.max(current, 0), safeTotal);
  const filledWidth = Math.round((clampedCurrent / safeTotal) * PROGRESS_BAR_WIDTH);
  return `${clampedCurrent}/${safeTotal} [${"=".repeat(filledWidth)}${"-".repeat(PROGRESS_BAR_WIDTH - filledWidth)}]`;
}

/**
 * @returns {void}
 */
function clearProgressLine() {
  if (!stdout.isTTY) {
    return;
  }

  readline.cursorTo(stdout, 0);
  readline.clearLine(stdout, 0);
}

/**
 * @returns {ProgressState}
 */
function getProgressState() {
  if (progressState === null) {
    throw new Error("Progress state has not been initialized.");
  }

  return progressState;
}

/**
 * @returns {void}
 */
function renderProgress() {
  if (!stdout.isTTY) {
    return;
  }

  const progressState = getProgressState();
  const pageText = formatProgressBar(progressState.currentPageNumber, progressState.totalPages);
  const postText = formatProgressBar(progressState.processedPosts, progressState.totalPosts);
  const message = [
    `Pages ${pageText}`,
    `Posts ${postText}`,
    `saved ${progressState.savedCount}`,
    `skipped ${progressState.skippedCount}`,
    `failed ${progressState.failedCount}`,
  ].join(" | ");

  clearProgressLine();
  stdout.write(message);
}

/**
 * @param {string} message
 * @returns {void}
 */
function logProgressMessage(message) {
  if (!stdout.isTTY) {
    console.log(message);
    return;
  }

  clearProgressLine();
  console.log(message);
  if (progressState !== null) {
    renderProgress();
  }
}

/**
 * @returns {void}
 */
function finishProgress() {
  if (!stdout.isTTY) {
    return;
  }

  renderProgress();
  stdout.write("\n");
}

/**
 * @param {import("playwright").Page} page
 * @param {string} targetUrl
 * @returns {Promise<any>}
 */
async function fetchJsonInPage(page, targetUrl) {
  const { timeoutMs } = getRuntimeConfig();
  const result = await page.evaluate(async ({ url, timeoutMs: requestTimeoutMs }) => {
    const controller = new AbortController();
    const timer = requestTimeoutMs > 0 ? setTimeout(() => controller.abort(), requestTimeoutMs) : null;

    try {
      const response = await fetch(url, { credentials: "include", signal: controller.signal });
      const text = await response.text();
      return {
        ok: response.ok,
        status: response.status,
        text,
        contentType: response.headers.get("content-type"),
        url: response.url,
        timedOut: false,
        fetchError: "",
      };
    } catch (error) {
      const message = getErrorMessage(error);
      return {
        ok: false,
        status: 0,
        text: "",
        contentType: "",
        url,
        timedOut: requestTimeoutMs > 0 && message.toLowerCase().includes("abort"),
        fetchError: message,
      };
    } finally {
      if (timer !== null) {
        clearTimeout(timer);
      }
    }
  }, { url: targetUrl, timeoutMs });

  if (result.timedOut) {
    throw new Error(`Timed out fetching ${targetUrl}`);
  }

  if (result.fetchError) {
    throw new Error(`Failed to fetch ${targetUrl}: ${result.fetchError}`);
  }

  if (!result.ok) {
    if (result.status === 403 && result.text.includes("Just a moment")) {
      throw new Error(`Cloudflare challenge for ${targetUrl}`);
    }
    throw new Error(`HTTP ${result.status} for ${targetUrl}`);
  }

  try {
    return JSON.parse(result.text);
  } catch (error) {
    throw new Error(`Failed to parse JSON from ${result.url ?? targetUrl}`);
  }
}

/**
 * @param {any} payload
 * @returns {number}
 */
function parseTotalPosts(payload) {
  if (typeof payload === "number") {
    return payload;
  }

  if (!payload || typeof payload !== "object") {
    throw new Error(`Unexpected counts payload type: ${typeof payload}`);
  }

  const candidates = [payload.posts, payload.count, payload.post_count];
  if (payload.counts && typeof payload.counts === "object") {
    candidates.push(payload.counts.posts, payload.counts.count, payload.counts.post_count);
  }

  for (const candidate of candidates) {
    if (typeof candidate === "number") {
      return candidate;
    }
    if (typeof candidate === "string" && /^\d+$/.test(candidate)) {
      return Number(candidate);
    }
  }

  throw new Error(`Failed to parse total posts from counts payload: ${JSON.stringify(payload)}`);
}

/**
 * @param {import("playwright").Page} page
 * @param {number} pageNumber
 * @returns {Promise<any[]>}
 * 获取各post详细信息，分页查询
 */
async function fetchPosts(page, pageNumber) {
  const url = buildPostsApiUrl(pageNumber);
  const payload = await fetchJsonInPage(page, url);
  if (!Array.isArray(payload)) {
    throw new Error(`Unexpected posts payload type for ${url}`);
  }
  return payload;
}

/**
 * @param {import("playwright").Page} page
 * @returns {Promise<any[][]>}
 * 获取post的详细信息
 */
async function prefetchPostsPages(page) {
  const pages = [];
  for (let pageNumber = 1; ; pageNumber += 1) {
    console.log(`Prefetching page ${pageNumber} to determine total pages...`);
    const posts = await fetchPosts(page, pageNumber);
    if (posts.length === 0) {
      break;
    }

    pages.push(posts);
    if (posts.length < POSTS_PER_PAGE) {
      break;
    }
  }
  return pages;
}

/**
 * @param {import("playwright").Page} page
 * @returns {Promise<{ totalPages: number, totalPosts: number, cachedPages: any[][] | null }>}
 * 返回任务总览（总数、各post信息）
 */
async function fetchTotalPages(page) {
  const countsUrl = buildCountsApiUrl();

  try {
    const payload = await fetchJsonInPage(page, countsUrl);
    const totalPosts = parseTotalPosts(payload);
    console.log(`Total posts: ${totalPosts}`);
    return { totalPages: Math.max(Math.ceil(totalPosts / POSTS_PER_PAGE), 1), totalPosts, cachedPages: null };
  } catch (error) {
    const message = getErrorMessage(error);
    if (message.includes("Cloudflare challenge")) {
      console.log(`Counts endpoint blocked, fallback to paging posts: ${countsUrl}`);
      const cachedPages = await prefetchPostsPages(page);
      const totalPosts = cachedPages.reduce((sum, posts) => sum + posts.length, 0);
      console.log(`Total posts: ${totalPosts}`);
      return { totalPages: Math.max(cachedPages.length, 1), totalPosts, cachedPages };
    }
    throw error;
  }
}

/**
 * @param {import("playwright").Page} downloadPage
 * @param {string} postUrl
 * @returns {Promise<string>}
 * 分析post页面，获取即将下载的文件名
 */
async function prepareDownload(downloadPage, postUrl) {
  const { output, timeoutMs } = getRuntimeConfig();
  await downloadPage.goto(postUrl, { waitUntil: "domcontentloaded", timeout: timeoutMs });
  await waitForChallengeClear(downloadPage);

  const downloadLink = downloadPage.getByRole("link", { name: /^Download$/ });
  await downloadLink.waitFor({ state: "visible", timeout: timeoutMs });
  const downloadHref = await downloadLink.getAttribute("href");
  if (!downloadHref) {
    throw new Error(`Download link missing href: ${postUrl}`);
  }

  const downloadUrl = new URL(downloadHref, postUrl).toString();
  const downloadAttribute = await downloadLink.getAttribute("download");
  const outputPath = path.join(output, resolveDownloadFilename(downloadUrl, downloadAttribute));

  return outputPath;
}

/**
 * @param {import("playwright").Page} downloadPage
 * @param {string} outputPath
 * @returns {Promise<void>}
 * 执行文件下载
 */
async function downloadPostAsset(downloadPage, outputPath) {
  const { timeoutMs } = getRuntimeConfig();
  const downloadLink = downloadPage.getByRole("link", { name: /^Download$/ });
  const [download] = await Promise.all([
    downloadPage.waitForEvent("download", { timeout: timeoutMs }),
    downloadLink.click(),
  ]);

  await download.saveAs(outputPath);
}

/**
 * @param {number} totalPages
 * @param {number} totalPosts
 * @returns {void}
 */
function createProgressState(totalPages, totalPosts) {
  progressState = {
    totalPages,
    totalPosts: Math.max(totalPosts, 1),
    currentPageNumber: 0,
    processedPosts: 0,
    savedCount: 0,
    skippedCount: 0,
    failedCount: 0,
  };
}

/**
 * @param {import("playwright").Page} downloadPage
 * @param {any[]} posts
 * @param {number} pageNumber
 * @param {Set<string>} seenPostIds
 * @returns {Promise<void>}
 */
async function processPosts(downloadPage, posts, pageNumber, seenPostIds) {
  const progressState = getProgressState();
  const existingFileHashes = getExistingFileHashes();
  progressState.currentPageNumber = pageNumber;

  if (!stdout.isTTY) {
    console.log(`[${pageNumber}/${progressState.totalPages}] posts: ${posts.length}`);
  } else {
    renderProgress();
  }

  for (let index = 0; index < posts.length; index += 1) {
    const post = posts[index];
    const postId = getPostId(post);
    if (!postId) {
      progressState.processedPosts += 1;
      progressState.skippedCount += 1;
      renderProgress();
      continue;
    }

    if (seenPostIds.has(postId)) {
      progressState.processedPosts += 1;
      progressState.skippedCount += 1;
      renderProgress();
      continue;
    }

    // 使用hash跳过已存在文件，hash由API获得，无需加载post页面
    const postHash = getPostHash(post);
    if (postHash && existingFileHashes.has(postHash)) {
      progressState.processedPosts += 1;
      progressState.skippedCount += 1;
      renderProgress();
      continue;
    }

    seenPostIds.add(postId);
    const postUrl = buildPostUrl(postId);
    let outputPath;

    try {
      outputPath = await prepareDownload(downloadPage, postUrl);
    } catch (error) {
      progressState.processedPosts += 1;
      progressState.failedCount += 1;
      logProgressMessage(`Failed page ${pageNumber} post ${index + 1}: ${getErrorMessage(error)}`);
      renderProgress();
      await delay(REQUEST_DELAY_MS);
      continue;
    }

    // 文件名存在跳过（虽然肯定会被前面的hash判断拦住，但还是兜一下底）
    if (await fileExists(outputPath)) {
      if (postHash) {
        existingFileHashes.add(postHash);
      }
      await rememberExistingFileHashes(outputPath);
      progressState.processedPosts += 1;
      progressState.skippedCount += 1;
      renderProgress();
      continue;
    }

    try {
      await downloadPostAsset(downloadPage, outputPath);
      if (postHash) {
        existingFileHashes.add(postHash);
      }
      await rememberExistingFileHashes(outputPath);
      progressState.processedPosts += 1;
      progressState.savedCount += 1;
    } catch (error) {
      progressState.processedPosts += 1;
      progressState.failedCount += 1;
      logProgressMessage(`Failed page ${pageNumber} post ${index + 1}: ${getErrorMessage(error)}`);
    }

    renderProgress();
    await delay(REQUEST_DELAY_MS);
  }
}

/**
 * @returns {Promise<void>}
 */
async function main() {
  const args = parseArgs(process.argv.slice(2));
  initializeRuntimeConfig(args);
  const requireFromPlaywright = createRequire(path.join(args.playwrightPackageDir, "package.json"));
  const { chromium } = requireFromPlaywright("playwright");

  await fs.mkdir(args.output, { recursive: true });
  await fs.mkdir(args.profileDir, { recursive: true });
  const existingFileHashesPromise = initializeExistingFileHashes(args.output);

  const context = await chromium.launchPersistentContext(args.profileDir, {
    headless: args.headless,
    viewport: null,
    acceptDownloads: true,
  });

  try {
    const page = context.pages()[0] ?? (await context.newPage());
    await page.goto(args.url, { waitUntil: "domcontentloaded", timeout: args.timeoutMs });
    await waitForChallengeClear(page);

    const { totalPages, totalPosts, cachedPages } = await fetchTotalPages(page);
    console.log(`Total pages: ${totalPages}`);

    const downloadPage = await context.newPage();
    const seenPostIds = new Set();
    createProgressState(totalPages, totalPosts);
    await existingFileHashesPromise;

    for (let pageNumber = 1; pageNumber <= totalPages; pageNumber += 1) {
      const posts = cachedPages ? cachedPages[pageNumber - 1] : await fetchPosts(page, pageNumber);
      await processPosts(downloadPage, posts, pageNumber, seenPostIds);
    }

    finishProgress();
  } finally {
    await context.close();
  }
}

main().catch((error) => {
  clearProgressLine();
  console.error(getErrorMessage(error));
  process.exit(1);
});
