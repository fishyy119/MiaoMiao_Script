const fs = require("node:fs/promises");
const path = require("node:path");
const readline = require("node:readline");
const readlinePromises = require("node:readline/promises");
const { stdin, stdout } = require("node:process");
const { createRequire } = require("node:module");

const REQUEST_DELAY_MS = 500;
const POSTS_PER_PAGE = 200;
const PROGRESS_BAR_WIDTH = 20;

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

function parseArgs(argv) {
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

function buildApiQueryParams(baseUrl) {
  const parsed = new URL(baseUrl);
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

function buildPostsApiUrl(baseUrl, page) {
  const parsed = new URL(baseUrl);
  const queryParams = buildApiQueryParams(baseUrl);
  queryParams.delete("z");
  queryParams.set("page", String(page));
  queryParams.set("limit", String(POSTS_PER_PAGE));
  parsed.pathname = "/posts.json";
  parsed.search = queryParams.toString();
  parsed.hash = "";
  return parsed.toString();
}

function buildCountsApiUrl(baseUrl) {
  const parsed = new URL(baseUrl);
  const queryParams = buildApiQueryParams(baseUrl);
  queryParams.delete("z");
  queryParams.delete("page");
  queryParams.delete("limit");
  parsed.pathname = "/counts/posts.json";
  parsed.search = queryParams.toString();
  parsed.hash = "";
  return parsed.toString();
}

function parseImageUrl(baseUrl, post) {
  if (!post || typeof post !== "object") {
    return null;
  }

  for (const key of ["file_url", "large_file_url", "preview_file_url"]) {
    const value = post[key];
    if (typeof value === "string" && value.length > 0) {
      return new URL(value, baseUrl).toString();
    }
  }

  return null;
}

function getFilenameFromUrl(url) {
  const parsed = new URL(url);
  const filename = path.posix.basename(parsed.pathname);
  if (!filename) {
    throw new Error(`Invalid image URL: ${url}`);
  }
  return filename;
}

async function delay(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function isChallengePage(page) {
  const title = await page.title();
  if (title.includes("Just a moment")) {
    return true;
  }

  const bodyText = await page.locator("body").innerText().catch(() => "");
  return bodyText.includes("Enable JavaScript and cookies to continue");
}

async function waitForChallengeClear(page, headless) {
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

function formatProgressBar(current, total) {
  const safeTotal = Math.max(total, 1);
  const clampedCurrent = Math.min(Math.max(current, 0), safeTotal);
  const filledWidth = Math.round((clampedCurrent / safeTotal) * PROGRESS_BAR_WIDTH);
  return `${clampedCurrent}/${safeTotal} [${"=".repeat(filledWidth)}${"-".repeat(PROGRESS_BAR_WIDTH - filledWidth)}]`;
}

function clearProgressLine() {
  if (!stdout.isTTY) {
    return;
  }

  readline.cursorTo(stdout, 0);
  readline.clearLine(stdout, 0);
}

function renderProgress(progressState) {
  if (!stdout.isTTY) {
    return;
  }

  const pageText = formatProgressBar(progressState.currentPageNumber, progressState.totalPages);
  const postText = formatProgressBar(progressState.processedPosts, progressState.totalPosts);
  const currentPagePost = `${Math.min(progressState.currentPagePostIndex, progressState.currentPagePosts)}/${Math.max(progressState.currentPagePosts, 1)}`;
  const message = [
    `Pages ${pageText}`,
    `Posts ${postText}`,
    `Current ${currentPagePost}`,
    `saved ${progressState.savedCount}`,
    `skipped ${progressState.skippedCount}`,
    `failed ${progressState.failedCount}`,
  ].join(" | ");

  clearProgressLine();
  stdout.write(message);
}

function logProgressMessage(message, progressState = null) {
  if (!stdout.isTTY) {
    console.log(message);
    return;
  }

  clearProgressLine();
  console.log(message);
  if (progressState) {
    renderProgress(progressState);
  }
}

function finishProgress(progressState) {
  if (!stdout.isTTY) {
    return;
  }

  renderProgress(progressState);
  stdout.write("\n");
}

async function fetchJsonInPage(page, targetUrl, timeoutMs) {
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
      const message = error instanceof Error ? error.message : String(error);
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

async function fetchPosts(page, baseUrl, pageNumber, timeoutMs) {
  const url = buildPostsApiUrl(baseUrl, pageNumber);
  const payload = await fetchJsonInPage(page, url, timeoutMs);
  if (!Array.isArray(payload)) {
    throw new Error(`Unexpected posts payload type for ${url}`);
  }
  return payload;
}

async function prefetchPostsPages(page, baseUrl, timeoutMs) {
  const pages = [];
  for (let pageNumber = 1; ; pageNumber += 1) {
    console.log(`Prefetching page ${pageNumber} to determine total pages...`);
    const posts = await fetchPosts(page, baseUrl, pageNumber, timeoutMs);
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

async function fetchTotalPages(page, baseUrl, timeoutMs) {
  const countsUrl = buildCountsApiUrl(baseUrl);

  try {
    const payload = await fetchJsonInPage(page, countsUrl, timeoutMs);
    const totalPosts = parseTotalPosts(payload);
    console.log(`Total posts: ${totalPosts}`);
    return { totalPages: Math.max(Math.ceil(totalPosts / POSTS_PER_PAGE), 1), totalPosts, cachedPages: null };
  } catch (error) {
    if (String(error.message).includes("Cloudflare challenge")) {
      console.log(`Counts endpoint blocked, fallback to paging posts: ${countsUrl}`);
      const cachedPages = await prefetchPostsPages(page, baseUrl, timeoutMs);
      const totalPosts = cachedPages.reduce((sum, posts) => sum + posts.length, 0);
      console.log(`Total posts: ${totalPosts}`);
      return { totalPages: Math.max(cachedPages.length, 1), totalPosts, cachedPages };
    }
    throw error;
  }
}

async function downloadImage(downloadPage, imageUrl, outputDir, timeoutMs) {
  const outputPath = path.join(outputDir, getFilenameFromUrl(imageUrl));

  try {
    await fs.access(outputPath);
    return "skipped";
  } catch {}

  const response = await downloadPage.goto(imageUrl, { waitUntil: "domcontentloaded", timeout: timeoutMs });
  if (!response || !response.ok()) {
    throw new Error(`Failed to fetch image: ${imageUrl}`);
  }

  const buffer = await response.body();
  await fs.writeFile(outputPath, buffer);
  return "saved";
}

function createProgressState(totalPages, totalPosts) {
  return {
    totalPages,
    totalPosts: Math.max(totalPosts, 1),
    currentPageNumber: 0,
    currentPagePosts: 0,
    currentPagePostIndex: 0,
    processedPosts: 0,
    savedCount: 0,
    skippedCount: 0,
    failedCount: 0,
  };
}

async function processPosts(downloadPage, baseUrl, posts, pageNumber, totalPages, outputDir, timeoutMs, seenUrls, progressState) {
  progressState.currentPageNumber = pageNumber;
  progressState.currentPagePosts = posts.length;
  progressState.currentPagePostIndex = 0;

  if (!stdout.isTTY) {
    console.log(`[${pageNumber}/${totalPages}] posts: ${posts.length}`);
  } else {
    renderProgress(progressState);
  }

  for (let index = 0; index < posts.length; index += 1) {
    progressState.currentPagePostIndex = index + 1;
    const imageUrl = parseImageUrl(baseUrl, posts[index]);
    if (!imageUrl) {
      progressState.processedPosts += 1;
      progressState.skippedCount += 1;
      renderProgress(progressState);
      continue;
    }

    if (seenUrls.has(imageUrl)) {
      progressState.processedPosts += 1;
      progressState.skippedCount += 1;
      renderProgress(progressState);
      continue;
    }

    seenUrls.add(imageUrl);

    try {
      const result = await downloadImage(downloadPage, imageUrl, outputDir, timeoutMs);
      progressState.processedPosts += 1;
      if (result === "saved") {
        progressState.savedCount += 1;
      } else {
        progressState.skippedCount += 1;
      }
    } catch (error) {
      progressState.processedPosts += 1;
      progressState.failedCount += 1;
      logProgressMessage(`Failed page ${pageNumber} post ${index + 1}: ${error.message}`, progressState);
    }

    renderProgress(progressState);
    await delay(REQUEST_DELAY_MS);
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const requireFromPlaywright = createRequire(path.join(args.playwrightPackageDir, "package.json"));
  const { chromium } = requireFromPlaywright("playwright");

  await fs.mkdir(args.output, { recursive: true });
  await fs.mkdir(args.profileDir, { recursive: true });

  const context = await chromium.launchPersistentContext(args.profileDir, {
    headless: args.headless,
    viewport: null,
  });

  try {
    const page = context.pages()[0] ?? (await context.newPage());
    await page.goto(args.url, { waitUntil: "domcontentloaded", timeout: args.timeoutMs });
    await waitForChallengeClear(page, args.headless);

    const { totalPages, totalPosts, cachedPages } = await fetchTotalPages(page, args.url, args.timeoutMs);
    console.log(`Total pages: ${totalPages}`);

    const downloadPage = await context.newPage();
    const seenUrls = new Set();
    const progressState = createProgressState(totalPages, totalPosts);

    for (let pageNumber = 1; pageNumber <= totalPages; pageNumber += 1) {
      const posts = cachedPages ? cachedPages[pageNumber - 1] : await fetchPosts(page, args.url, pageNumber, args.timeoutMs);
      await processPosts(downloadPage, args.url, posts, pageNumber, totalPages, args.output, args.timeoutMs, seenUrls, progressState);
    }

    finishProgress(progressState);
  } finally {
    await context.close();
  }
}

main().catch((error) => {
  clearProgressLine();
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
