<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { Connection, MagicStick } from '@element-plus/icons-vue'
import http, { ApiError } from '../api'
import StatePanel from './StatePanel.vue'
import MoviePoster from './MoviePoster.vue'
import type { AlgorithmResult, Movie } from '../types'
const props = withDefaults(defineProps<{ endpoint: string | null; label: string; emptySubject?: string }>(), { emptySubject: '登录后体验' })
const loading = ref(false), error = ref<unknown>(null), unavailable = ref(false)
const result = ref<AlgorithmResult | null>(null), movies = ref<Movie[]>([])
const movieById = computed(() => new Map(movies.value.map(movie => [movie.movie_id, movie])))
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
    const details = await Promise.all(response.data.items.map(async item => {
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
function scoreLabel(score: number | null) { return score === null ? '未提供匹配分' : `${Math.round(score * 100)}% 类型匹配` }
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
</script>
<template>
  <section class="algorithm-panel" :aria-label="label">
    <div class="section-top recommendation-heading"><div><span class="small-label">RECOMMENDATION OUTPUT</span><h3>{{ label }}</h3></div><el-button text :icon="MagicStick" :loading="loading" @click="load">刷新结果</el-button></div>
    <StatePanel :loading="loading" :error="error" @retry="load">
      <div v-if="!endpoint || unavailable" class="algorithm-empty" role="status">
        <div class="algorithm-symbol"><el-icon aria-hidden="true"><Connection /></el-icon></div>
        <div><span class="status-pill">{{ !endpoint ? emptySubject : '尚未实现' }}</span><h3>{{ !endpoint ? '选择观众，开始探索' : '下一部好电影，等待算法发现' }}</h3><p>{{ !endpoint ? '先选择历史用户或登录注册账号。推荐功能等待算法接入。' : '等待算法接入；当前没有模型版本或推荐结果。' }}</p></div>
        <RouterLink v-if="!endpoint && emptySubject === '登录后体验'" class="text-link" to="/login">前往登录 →</RouterLink>
      </div>
      <div v-else-if="result" class="recommendation-results">
        <div class="recommendation-meta"><span>模型 <strong>{{ result.model_version }}</strong></span><span>{{ result.dataset_version }}</span><span>{{ result.items.length }} 部候选电影</span></div>
        <p v-if="!result.items.length" class="no-results">这位观众尚无足够的高评分历史，暂时无法构建内容偏好画像。</p>
        <div v-else class="recommendation-grid">
          <RouterLink v-for="item in result.items" :key="item.movie_id" class="recommendation-card" :class="rankClass(item.rank)" :to="`/movies/${item.movie_id}`">
            <div class="recommendation-poster">
              <MoviePoster :path="movieById.get(item.movie_id)?.poster_path" :title="movieById.get(item.movie_id)?.title_zh || movieById.get(item.movie_id)?.movielens_title || `电影 #${item.movie_id}`" />
              <span class="recommendation-rank" :class="rankClass(item.rank)">{{ rankIcon(item.rank) }} {{ String(item.rank).padStart(2, '0') }}</span>
            </div>
            <div class="recommendation-copy">
              <div class="recommendation-score-row">
                <span class="recommendation-score">{{ scoreLabel(item.score) }}</span>
                <div v-if="item.score !== null" class="score-bar"><div class="score-bar-fill" :style="{ width: (item.score * 100).toFixed(1) + '%' }" /></div>
              </div>
              <h4>{{ movieById.get(item.movie_id)?.title_zh || movieById.get(item.movie_id)?.movielens_title || `电影 #${item.movie_id}` }}</h4>
              <p class="recommendation-meta-line">{{ movieById.get(item.movie_id)?.release_year || '年份未收录' }} <span aria-hidden="true">·</span> {{ movieById.get(item.movie_id)?.genres.slice(0, 2).join(' / ') || '类型资料加载中' }}</p>
            </div>
          </RouterLink>
        </div>
      </div>
    </StatePanel>
  </section>
</template>

<style scoped>
.recommendation-heading h3{margin-top:3px}.recommendation-heading .small-label{font-size:9px}.recommendation-results{padding:22px 24px 26px}.recommendation-meta{display:flex;flex-wrap:wrap;gap:8px 18px;color:var(--muted);font-size:11px;padding-bottom:17px;border-bottom:1px solid var(--border)}.recommendation-meta strong,.recommendation-score{color:var(--accent)}.recommendation-meta strong{font-weight:600}.recommendation-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:16px;margin-top:20px}.recommendation-card{min-width:0;border-radius:10px;padding:9px;border:1px solid var(--border);transition:background .22s,border-color .22s,transform .22s,box-shadow .22s;background:linear-gradient(160deg,rgba(179,136,255,0.04),transparent 60%)}.recommendation-card:hover{background:rgba(179,136,255,0.07);border-color:var(--accent);transform:translateY(-6px);box-shadow:0 10px 28px -6px rgba(179,136,255,0.35)}.recommendation-poster{position:relative}.recommendation-poster :deep(.movie-poster){aspect-ratio:3 / 3.7;border-radius:7px}.recommendation-rank{position:absolute;top:8px;left:8px;min-width:34px;padding:4px 7px;text-align:center;border-radius:14px;background:rgba(15,8,32,0.85);border:1px solid rgba(255,255,255,0.18);color:var(--accent);font:700 11px ui-monospace,monospace;backdrop-filter:blur(4px);letter-spacing:.5px}.recommendation-rank.rank-gold{background:linear-gradient(135deg,#f5c85a,#e09b2d);border-color:#ffd97a;color:#1a0f25;box-shadow:0 0 14px rgba(245,200,90,0.5)}.recommendation-rank.rank-silver{background:linear-gradient(135deg,#d6dae3,#9aa2b4);border-color:#f0f3f8;color:#1a0f25;box-shadow:0 0 12px rgba(214,218,227,0.4)}.recommendation-rank.rank-bronze{background:linear-gradient(135deg,#c98a5a,#8b5a32);border-color:#e6a36f;color:#1a0f25;box-shadow:0 0 10px rgba(201,138,90,0.35)}.recommendation-copy{padding:10px 4px 4px}.recommendation-score-row{display:flex;align-items:center;gap:8px;margin-bottom:4px}.recommendation-score{font-size:10px;letter-spacing:.03em;white-space:nowrap}.score-bar{flex:1;height:4px;background:rgba(179,136,255,0.15);border-radius:2px;overflow:hidden}.score-bar-fill{height:100%;background:linear-gradient(90deg,var(--accent),#d4aaff);border-radius:2px;transition:width .6s ease}.recommendation-copy h4{margin:6px 0 0;font-size:13px;line-height:1.45;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.recommendation-meta-line{color:var(--muted);font-size:10px;line-height:1.5;margin:5px 0 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.no-results{padding:26px 0 4px;color:var(--muted);font-size:13px}@media(max-width:1050px){.recommendation-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:620px){.recommendation-results{padding:18px}.recommendation-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}</style>
