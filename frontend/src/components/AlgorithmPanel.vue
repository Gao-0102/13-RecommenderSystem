<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { Connection, MagicStick, ChatDotRound } from '@element-plus/icons-vue'
import http, { ApiError } from '../api'
import StatePanel from './StatePanel.vue'
import MoviePoster from './MoviePoster.vue'
import type { AlgorithmResult, Movie } from '../types'
const props = withDefaults(defineProps<{ endpoint: string | null; label: string; emptySubject?: string; columns?: number; limit?: number }>(), { emptySubject: '登录后体验', columns: 5, limit: 0 })
const loading = ref(false), error = ref<unknown>(null), unavailable = ref(false)
const result = ref<AlgorithmResult | null>(null), movies = ref<Movie[]>([])
const explainDialogVisible = ref(false), explainLoading = ref(false), explainText = ref(''), explainError = ref('')
const movieById = computed(() => new Map(movies.value.map(movie => [movie.movie_id, movie])))
const visibleItems = computed(() => {
  const items = result.value?.items ?? []
  return props.limit > 0 ? items.slice(0, props.limit) : items
})
const metaText = computed(() => {
  const total = result.value?.items.length ?? 0
  if (props.limit > 0 && total > props.limit) return `精选 ${visibleItems.value.length} 部 · 共 ${total} 部`
  return `为你找到 ${total} 部电影`
})
let run = 0
onScopeDispose(() => { run++ })
async function load() {
  const seq = ++run
  error.value = null; result.value = null; movies.value = []; unavailable.value = false; loading.value = false
  if (!props.endpoint) return
  loading.value = true
  try {
    const response = await http.get<AlgorithmResult>(props.endpoint)
    if (seq !== run) return
    result.value = response.data
    const visibleItems = props.limit > 0 ? response.data.items.slice(0, props.limit) : response.data.items
    const details = await Promise.all(visibleItems.map(async item => {
      try { return (await http.get<Movie>(`/movies/${item.movie_id}`)).data } catch { return null }
    }))
    if (seq === run) movies.value = details.filter((movie): movie is Movie => movie !== null)
  }
  catch (e) {
    if (seq !== run) return
    if (e instanceof ApiError && e.status === 501 && e.code === 'ALGORITHM_NOT_IMPLEMENTED') unavailable.value = true
    else error.value = e
  } finally { if (seq === run) loading.value = false }
}
function isPopularScore(item: AlgorithmResult['items'][number]) {
  if (item.algorithm === 'popular') return true
  if (item.algorithm === 'cold_start') return !!item.recall_sources?.includes('cold_start:popular')
  return false
}
const sourceLabelMap: Record<string, string> = { content: 'Content', itemcf: 'ItemCF', als: 'ALS', popular: 'Popular' }
function sourceLabel(alg: string) { return sourceLabelMap[alg] || alg }
function scoreText(item: AlgorithmResult['items'][number]) {
  if (item.score === null) return '暂无评分'
  if (isPopularScore(item)) return `综合评分 ${(item.score * 4 + 1).toFixed(2)} / 5`
  if (item.algorithm === 'itemcf') return `行为相似度 ${Math.round(item.score * 100)}%`
  if (item.algorithm === 'rrf') return `融合分 ${item.score.toFixed(4)}`
  return `${Math.round(item.score * 100)}% 类型匹配`
}
function rankBadges(item: AlgorithmResult['items'][number]) {
  if (item.algorithm !== 'rrf' || !item.recall_ranks) return []
  return Object.entries(item.recall_ranks).map(([alg, rank]) => `${sourceLabel(alg)} #${rank}`)
}
function heatText(item: AlgorithmResult['items'][number]) {
  if (item.score === null || !isPopularScore(item)) return ''
  return `热度 ${Math.round(item.score * 100)}%`
}
function rankClass(rank: number) {
  if (rank === 1) return 'rank-gold'
  if (rank === 2) return 'rank-silver'
  if (rank === 3) return 'rank-bronze'
  return 'rank-normal'
}
function rankIcon(rank: number) {
  if (rank === 1) return '★'
  if (rank === 2) return '☆'
  if (rank === 3) return '✦'
  return ''
}
watch(() => props.endpoint, load, { immediate: true })

const explainEndpoint = computed(() => props.endpoint ? props.endpoint + '/explain' : null)
async function fetchExplain() {
  if (!explainEndpoint.value) return
  explainDialogVisible.value = true
  explainLoading.value = true
  explainError.value = ''
  explainText.value = ''
  try {
    const resp = await http.get<{ algorithm: string; explanation: string; evidence: any }>(explainEndpoint.value)
    explainText.value = resp.data.explanation
  } catch (e) {
    explainError.value = e instanceof ApiError ? `${e.status} ${e.message}` : String(e)
  } finally { explainLoading.value = false }
}
</script>
<template>
  <section class="algorithm-panel" :aria-label="label">
    <div class="section-top recommendation-heading"><div><span class="small-label">推荐片单</span><h3>{{ label }}</h3></div><div class="heading-btns"><el-button text :icon="MagicStick" :loading="loading" @click="load">刷新结果</el-button><el-button text :icon="ChatDotRound" :loading="explainLoading" :disabled="!endpoint || unavailable" @click="fetchExplain">推荐理由</el-button></div></div>
    <StatePanel :loading="loading" :error="error" @retry="load">
      <div v-if="!endpoint || unavailable" class="algorithm-empty" role="status">
        <div class="algorithm-symbol"><el-icon aria-hidden="true"><Connection /></el-icon></div>
        <div><span class="status-pill">{{ !endpoint ? emptySubject : '即将上线' }}</span><h3>{{ !endpoint ? (emptySubject === '登录后体验' ? '登录后开启专属推荐' : '选择一位观众，开始探索') : '下一部好电影，等待发现' }}</h3><p>{{ !endpoint ? (emptySubject === '登录后体验' ? '你的评分与收藏，将用来生成个性化片单。' : '从左侧选择一位历史观众，即可查看为他生成的片单。') : '该推荐策略暂未开放，敬请期待。' }}</p></div>
        <RouterLink v-if="!endpoint && emptySubject === '登录后体验'" class="text-link" to="/login">前往登录 →</RouterLink>
      </div>
      <div v-else-if="result" class="recommendation-results">
        <div class="recommendation-meta"><span>{{ metaText }}</span></div>
        <p v-if="!result.items.length" class="no-results">暂时没有可推荐的电影，过段时间再来看看吧。</p>
        <div v-else class="recommendation-grid" :class="`cols-${columns}`">
          <RouterLink v-for="item in visibleItems" :key="item.movie_id" class="recommendation-card" :class="rankClass(item.rank)" :to="`/movies/${item.movie_id}`">
            <div class="recommendation-poster">
              <MoviePoster :path="movieById.get(item.movie_id)?.poster_path" :title="movieById.get(item.movie_id)?.title_zh || movieById.get(item.movie_id)?.movielens_title || `电影 #${item.movie_id}`" />
              <span class="recommendation-rank" :class="rankClass(item.rank)">{{ rankIcon(item.rank) }} {{ String(item.rank).padStart(2, '0') }}</span>
            </div>
            <div class="recommendation-copy">
              <div class="recommendation-score-row">
                <span class="recommendation-score">{{ scoreText(item) }}</span>
                <span v-if="heatText(item)" class="recommendation-heat">{{ heatText(item) }}</span>
              </div>
              <div v-if="item.algorithm === 'rrf' && rankBadges(item).length" class="rrf-badges">
                <span v-for="badge in rankBadges(item)" :key="badge" class="rrf-badge">{{ badge }}</span>
              </div>
              <h4>{{ movieById.get(item.movie_id)?.title_zh || movieById.get(item.movie_id)?.movielens_title || `电影 #${item.movie_id}` }}</h4>
              <p class="recommendation-meta-line">{{ movieById.get(item.movie_id)?.release_year || '年份未收录' }} <span aria-hidden="true">·</span> {{ movieById.get(item.movie_id)?.genres.slice(0, 2).join(' / ') || '类型资料加载中' }}</p>
            </div>
          </RouterLink>
        </div>
      </div>
    </StatePanel>
    <el-dialog v-model="explainDialogVisible" title="🤖 推荐理由（大模型可核验解释）" width="min(720px, 92vw)" :close-on-click-modal="false" destroy-on-close>
      <div v-if="explainLoading" class="explain-loading"><el-icon class="is-loading"><MagicStick /></el-icon><span>正在调用大模型，基于你的真实历史评分和推荐算法证据生成解释…</span></div>
      <div v-else-if="explainError" class="explain-error"><el-alert type="error" :closable="false">{{ explainError }}</el-alert></div>
      <div v-else class="explain-content"><pre class="explain-text">{{ explainText }}</pre></div>
    </el-dialog>
  </section>
</template>

<style scoped>
.recommendation-heading h3{margin-top:3px}.recommendation-heading .small-label{font-size:9px}.recommendation-results{padding:22px 24px 26px}.recommendation-meta{display:flex;flex-wrap:wrap;gap:8px 18px;color:var(--muted);font-size:11px;padding-bottom:17px;border-bottom:1px solid var(--border)}.recommendation-meta strong,.recommendation-score{color:var(--accent)}.recommendation-meta strong{font-weight:600}.recommendation-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:16px;margin-top:20px}.recommendation-grid.cols-2{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.recommendation-grid.cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}.recommendation-grid.cols-4{grid-template-columns:repeat(4,minmax(0,1fr))}.recommendation-card{min-width:0;border-radius:10px;padding:9px;border:1px solid var(--border);transition:background .22s,border-color .22s,transform .22s,box-shadow .22s;background:linear-gradient(160deg,rgba(14,165,165,0.05),transparent 60%)}.recommendation-card:hover{background:rgba(14,165,165,0.08);border-color:var(--accent);transform:translateY(-6px);box-shadow:0 10px 28px -6px rgba(14,165,165,0.25)}.recommendation-poster{position:relative}.recommendation-poster :deep(.movie-poster){aspect-ratio:3 / 3.7;border-radius:7px}.recommendation-rank{position:absolute;top:8px;left:8px;min-width:34px;padding:4px 7px;text-align:center;border-radius:14px;background:rgba(15,8,32,0.85);border:1px solid rgba(255,255,255,0.18);color:var(--accent);font:700 11px ui-monospace,monospace;backdrop-filter:blur(4px);letter-spacing:.5px}.recommendation-rank.rank-gold{background:linear-gradient(135deg,#f5c85a,#e09b2d);border-color:#ffd97a;color:#1a0f25;box-shadow:0 0 14px rgba(245,200,90,0.5)}.recommendation-rank.rank-silver{background:linear-gradient(135deg,#d6dae3,#9aa2b4);border-color:#f0f3f8;color:#1a0f25;box-shadow:0 0 12px rgba(214,218,227,0.4)}.recommendation-rank.rank-bronze{background:linear-gradient(135deg,#c98a5a,#8b5a32);border-color:#e6a36f;color:#1a0f25;box-shadow:0 0 10px rgba(201,138,90,0.35)}.recommendation-copy{padding:10px 4px 4px}.recommendation-score-row{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:4px}.recommendation-score{font-size:10px;letter-spacing:.03em;white-space:nowrap;color:var(--accent)}.recommendation-heat{font-size:9px;letter-spacing:.03em;white-space:nowrap;padding:2px 7px;border-radius:10px;color:var(--accent);background:rgba(14,165,165,0.10);border:1px solid rgba(14,165,165,0.25)}.rrf-badges{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}.rrf-badge{font-size:9px;letter-spacing:.03em;padding:2px 6px;border-radius:8px;color:#6366f1;background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.25);font-weight:600}.recommendation-copy h4{margin:6px 0 0;font-size:13px;line-height:1.45;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.recommendation-meta-line{color:var(--muted);font-size:10px;line-height:1.5;margin:5px 0 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.no-results{padding:26px 0 4px;color:var(--muted);font-size:13px}.heading-btns{display:flex;gap:4px}.explain-loading{display:flex;align-items:center;gap:10px;padding:30px;color:var(--muted);justify-content:center}.explain-error{padding:8px 0}.explain-content{max-height:60vh;overflow-y:auto}.explain-text{white-space:pre-wrap;font-family:Inter,"Microsoft YaHei",system-ui,sans-serif;font-size:14px;line-height:1.85;color:var(--text);margin:0;padding:0 4px}@media(max-width:1050px){.recommendation-grid:not(.cols-2):not(.cols-3){grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:620px){.recommendation-results{padding:18px}.recommendation-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}</style>
