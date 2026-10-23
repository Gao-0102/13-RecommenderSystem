<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowRight, Search, Reading } from '@element-plus/icons-vue'
import http from '../api'
import { useAuth } from '../stores/auth'
import { useRemote } from '../composables/useRemote'
import type { Movie, Page } from '../types'
import MovieCard from '../components/MovieCard.vue'
import StatePanel from '../components/StatePanel.vue'
import AlgorithmPanel from '../components/AlgorithmPanel.vue'
const auth = useAuth()
const { data, error, loading, load } = useRemote<Page<Movie>>()
const fetchMovies = () => load(async () => (await http.get<Page<Movie>>('/movies', { params: { per_page: 4 } })).data)
const heroImage = `https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=${encodeURIComponent('Bright cinematic editorial scene for a movie discovery website: elegant film reel and projector silhouette against soft teal and cyan gradient background, cool aqua light rays and floating translucent particles, mint and turquoise color palette, clean minimal composition, premium modern design aesthetic, no text, no watermark, soft diffused lighting')}&image_size=landscape_16_9`
onMounted(fetchMovies)

const historyCount = ref(0)
const historyLoaded = ref(false)
async function loadHistoryCount() {
  if (!auth.account) { historyCount.value = 0; historyLoaded.value = true; return }
  try {
    const [r, f] = await Promise.all([
      http.get<Page<unknown>>('/me/ratings', { params: { per_page: 1, page: 1 } }),
      http.get<Page<unknown>>('/me/favorites', { params: { per_page: 1, page: 1 } }),
    ])
    historyCount.value = (r.data.total ?? 0) + (f.data.total ?? 0)
  } catch { historyCount.value = 0 }
  historyLoaded.value = true
}
watch(() => auth.account, (a) => { historyLoaded.value = false; loadHistoryCount() }, { immediate: true })
const onRatingUpdated = () => { historyLoaded.value = false; loadHistoryCount() }
window.addEventListener('rating-updated', onRatingUpdated)
onBeforeUnmount(() => window.removeEventListener('rating-updated', onRatingUpdated))
</script>
<template>
  <div class="page home-page">
    <section class="hero">
      <div class="hero-copy"><p class="eyebrow"><span /> A MOMENT FOR CINEMA</p><h1>好电影，值得<span>再靠近一点。</span></h1><p class="hero-description">从一部电影开始，发现自己的观影偏好。<br />探索真实片库，让每一次评分留下回响。</p><div class="hero-actions"><RouterLink class="button primary" to="/movies">探索电影库 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink><RouterLink class="button subtle" to="/experiments">进入推荐实验室</RouterLink></div><div class="hero-footnote"><span class="line" /> 浏览 · 记录 · 发现</div></div>
      <div class="hero-art"><div class="orbital orbital-one" /><figure class="hero-frame"><img :src="heroImage" alt="清新蓝绿色调的电影放映机与胶片主题插画" /><figcaption><span>CINE DISCOVERY</span><strong>今晚，看什么？</strong></figcaption></figure></div>
    </section>
    <div class="intro-strip"><p><el-icon aria-hidden="true"><Reading /></el-icon><strong>真实片库</strong><span>来自真实观影社区的电影档案</span></p><p><el-icon aria-hidden="true"><Search /></el-icon><strong>自由探索</strong><span>按片名与类型发现电影</span></p><RouterLink to="/movies">开始浏览 <span aria-hidden="true">↗</span></RouterLink></div>
    <section class="recommendation-section"><div class="section-heading"><div><p class="eyebrow">MADE FOR YOUR TASTE</p><h2>你的下一部<span class="heading-dot">.</span></h2><p class="muted">根据你的评分与收藏，持续更新专属片单。</p></div><RouterLink to="/experiments" class="text-link">查看实验室 →</RouterLink></div><div v-if="auth.account && historyLoaded && historyCount > 0" class="recommendation-columns"><AlgorithmPanel label="为你推荐" :columns="2" :limit="4" :endpoint="'/me/recommendations/content'" /><AlgorithmPanel label="融合推荐 (RRF)" :columns="2" :limit="4" :endpoint="'/me/recommendations/rrf'" /></div><AlgorithmPanel :label="auth.account && historyLoaded && historyCount > 0 ? '热门推荐' : '热门精选'" :columns="5" :limit="10" :endpoint="auth.account && historyLoaded && historyCount > 0 ? '/me/recommendations/popular' : '/public/recommendations/popular'" :empty-subject="'热门片库'" /><p v-if="!auth.account" class="guest-hint">登录后开启专属推荐与融合推荐 →</p><p v-else-if="historyLoaded && historyCount === 0" class="guest-hint">给几部电影评分或加入收藏后，专属推荐与融合推荐将自动开启 →</p></section>
    <section class="browse-section"><div class="section-heading"><div><p class="eyebrow">THE FILM ARCHIVE</p><h2>从片库出发<span class="heading-dot">.</span></h2><p class="muted">从精心整理的电影档案里，挑一部今晚的电影。</p></div><RouterLink to="/movies" class="text-link">查看全部 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink></div><StatePanel :loading="loading" :error="error" :empty="!!data && !data.items.length" @retry="fetchMovies"><div class="movie-grid"><MovieCard v-for="movie in data?.items" :key="movie.movie_id" :movie="movie" /></div></StatePanel></section>
  </div>
</template>

<style scoped>
.hero { min-height: 0; padding: 40px 48px; grid-template-columns: 1.35fr .9fr; align-items: center; gap: 40px; }
.hero h1 { font-size: clamp(30px, 2.7vw, 40px); line-height: 1.32; margin: 12px 0; }
.hero .eyebrow { margin-bottom: 8px; }
.hero-description { font-size: 14px; line-height: 1.85; }
.hero-actions { margin-top: 22px; }
.hero-footnote { display: none; }
.hero-art { position: relative; min-height: 0; height: auto; display: flex; align-items: center; justify-content: center; transform: none; }
.hero-art .orbital { width: 340px; height: 340px; border-color: rgba(14, 165, 165, 0.12); left: 50%; top: 50%; margin: -170px 0 0 -170px; }
.hero-frame { position: relative; margin: 0; width: 100%; border-radius: 14px; overflow: hidden; border: 1px solid rgba(14, 165, 165, 0.25); box-shadow: 0 30px 70px -24px rgba(14, 165, 165, 0.28); transition: transform .3s ease, box-shadow .3s ease; }
.hero-frame:hover { transform: translateY(-4px); box-shadow: 0 38px 80px -22px rgba(14, 165, 165, 0.4); }
.hero-frame img { display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: cover; }
.hero-frame figcaption { position: absolute; inset: auto 0 0; padding: 44px 20px 16px; background: linear-gradient(to top, rgba(6, 64, 64, 0.85), transparent); display: flex; flex-direction: column; gap: 3px; }
.hero-frame figcaption span { font-size: 9px; letter-spacing: .28em; color: #B8E5E5; }
.hero-frame figcaption strong { font-size: 17px; font-weight: 600; color: #fff; letter-spacing: .02em; }
.recommendation-section { margin-top: 44px; }
@media (max-width: 1050px) {
  .hero { grid-template-columns: 1.2fr 1fr; padding: 32px 32px; gap: 28px; }
}
@media (max-width: 780px) {
  .hero { grid-template-columns: 1fr; padding: 28px 24px; gap: 22px; }
  .hero-art { width: 100%; }
  .hero-frame { max-width: 460px; }
}
@media (max-width: 540px) {
  .hero { padding: 24px 20px; }
  .hero h1 { font-size: 30px; }
  .hero-actions { gap: 10px; }
  .hero-actions .button { padding: 10px 12px; }
  .hero-art { display: flex; }
  .recommendation-section { margin-top: 30px; }
}
.guest-hint { grid-column: 1 / -1; color: var(--muted); font-size: 13px; padding: 14px 22px; border: 1px dashed var(--border); border-radius: 8px; text-align: center; margin-top: 4px; }
</style>
