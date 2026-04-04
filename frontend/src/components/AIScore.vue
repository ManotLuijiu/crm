<template>
  <div class="flex flex-col gap-1.5 border-b sm:px-6 py-3 px-4">
    <div class="flex items-center justify-between">
      <div class="text-sm text-ink-gray-5">AI Analysis</div>
      <Button
        v-if="data?.name"
        class="ml-auto"
        :label="isLoading ? 'Analyzing...' : 'Refresh'"
        :loading="isLoading"
        @click="refreshAnalysis"
      />
    </div>

    <div v-if="isLoading && !hasScore" class="py-2 text-sm text-ink-gray-4">
      Analyzing...
    </div>

    <template v-else-if="scoreData">
      <!-- AI Lead Score -->
      <div v-if="scoreData.score !== undefined" class="flex items-center gap-2">
        <div class="sm:w-[106px] w-36 text-sm text-ink-gray-5">Lead Score</div>
        <Tooltip :text="scoreData.summary || 'AI-calculated lead quality score'">
          <div class="flex items-center gap-2">
            <div
              class="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm font-semibold"
              :class="scoreColorClass"
            >
              {{ scoreData.score }}
            </div>
            <div class="text-sm">
              <span class="font-medium" :class="scoreTextClass">{{ scoreLabel }}</span>
              <span v-if="scoreData.confidence" class="text-ink-gray-4 text-xs ml-1">
                ({{ (scoreData.confidence * 100).toFixed(0) }}% confident)
              </span>
            </div>
          </div>
        </Tooltip>
      </div>

      <!-- AI Deal Probability -->
      <div v-if="scoreData.probability !== undefined" class="flex items-center gap-2">
        <div class="sm:w-[106px] w-36 text-sm text-ink-gray-5">AI Probability</div>
        <Tooltip :text="scoreData.summary || 'AI-predicted deal close probability'">
          <div class="flex items-center gap-2">
            <div
              class="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm font-semibold"
              :class="probabilityColorClass"
            >
              {{ scoreData.probability }}%
            </div>
            <div v-if="scoreData.confidence" class="text-xs text-ink-gray-4">
              {{ (scoreData.confidence * 100).toFixed(0) }}% confident
            </div>
          </div>
        </Tooltip>
      </div>

      <!-- AI Next Action -->
      <div v-if="scoreData.next_action" class="flex items-start gap-2">
        <div class="sm:w-[106px] w-36 text-sm text-ink-gray-5">Next Action</div>
        <div class="text-sm text-ink-gray-9 bg-surface-gray-2 px-2 py-1 rounded">
          {{ scoreData.next_action }}
        </div>
      </div>

      <!-- AI Confidence -->
      <div v-if="scoreData.confidence !== undefined && !scoreData.probability" class="flex items-center gap-2">
        <div class="sm:w-[106px] w-36 text-sm text-ink-gray-5">Confidence</div>
        <Tooltip :text="'How certain the AI is about this prediction'">
          <div class="w-full">
            <div class="w-full bg-surface-gray-2 rounded-full h-1.5">
              <div
                class="h-1.5 rounded-full"
                :class="confidenceBarClass"
                :style="{ width: `${scoreData.confidence * 100}%` }"
              />
            </div>
          </div>
        </Tooltip>
      </div>

      <!-- Score Factors (collapsible) -->
      <div v-if="scoreData.factors?.length" class="mt-2">
        <div
          class="flex items-center gap-1 text-xs text-ink-gray-4 cursor-pointer hover:text-ink-gray-6"
          @click="showFactors = !showFactors"
        >
          <component :is="showFactors ? 'FeatherIcon' : 'FeatherIcon'" :name="showFactors ? 'chevron-up' : 'chevron-down'" class="w-3 h-3" />
          {{ showFactors ? 'Hide' : 'Show' }} scoring factors
        </div>
        <div v-if="showFactors" class="mt-2 space-y-1">
          <div
            v-for="(factor, idx) in scoreData.factors"
            :key="idx"
            class="flex items-start gap-2 text-xs"
          >
            <span
              class="w-1.5 h-1.5 rounded-full mt-1 flex-shrink-0"
              :class="{
                'bg-green-500': factor.impact === 'positive',
                'bg-red-500': factor.impact === 'negative',
                'bg-gray-400': factor.impact === 'neutral',
              }"
            />
            <span class="text-ink-gray-6">{{ factor.description || factor.name }}</span>
          </div>
        </div>
      </div>

      <!-- Recommendations -->
      <div v-if="scoreData.recommendations?.length" class="mt-2">
        <div
          class="flex items-center gap-1 text-xs text-ink-gray-4 cursor-pointer hover:text-ink-gray-6"
          @click="showRecommendations = !showRecommendations"
        >
          <FeatherIcon :name="showRecommendations ? 'chevron-up' : 'chevron-down'" class="w-3 h-3" />
          {{ showRecommendations ? 'Hide' : 'Show' }} recommendations ({{ scoreData.recommendations.length }})
        </div>
        <div v-if="showRecommendations" class="mt-2 space-y-1">
          <div
            v-for="(rec, idx) in scoreData.recommendations"
            :key="idx"
            class="flex items-start gap-2 text-xs p-2 bg-surface-gray-2 rounded"
          >
            <span
              class="px-1 py-0.5 text-xs rounded"
              :class="{
                'bg-red-100 text-red-700': rec.priority === 'high',
                'bg-yellow-100 text-yellow-700': rec.priority === 'medium',
                'bg-gray-100 text-gray-600': rec.priority === 'low' || !rec.priority,
              }"
            >
              {{ rec.priority || 'normal' }}
            </span>
            <span class="text-ink-gray-6 flex-1">{{ rec.reason || rec.action }}</span>
          </div>
        </div>
      </div>

      <!-- Last Updated -->
      <div v-if="lastUpdated" class="text-xs text-ink-gray-4 mt-1">
        Updated {{ timeAgo(lastUpdated) }}
      </div>
    </template>

    <div v-else class="text-sm text-ink-gray-4 py-2">
      Enable AI in Settings to see analysis
    </div>
  </div>
</template>

<script setup>
import { FeatherIcon } from 'frappe-ui'
import { ref, computed } from 'vue'
import { timeAgo } from '@/utils'

const props = defineProps({
  doctype: {
    type: String,
    required: true,
    validator: (value) => ['CRM Lead', 'CRM Deal'].includes(value),
  },
})

const data = defineModel()
const emit = defineEmits(['updateField', 'refresh'])

const isLoading = ref(false)
const showFactors = ref(false)
const showRecommendations = ref(false)

const hasScore = computed(() => {
  if (!data.value) return false
  if (props.doctype === 'CRM Lead') {
    return data.value.ai_lead_score != null
  }
  if (props.doctype === 'CRM Deal') {
    return data.value.ai_probability != null
  }
  return false
})

const scoreData = computed(() => {
  if (!data.value) return null

  if (props.doctype === 'CRM Lead') {
    if (data.value.ai_lead_score == null) return null
    return {
      score: Math.round(data.value.ai_lead_score),
      confidence: data.value.ai_confidence,
      factors: data.value.ai_score_factors ? parseFactors(data.value.ai_score_factors) : [],
      summary: data.value.ai_summary,
      lastUpdated: data.value.ai_last_scored,
    }
  }

  if (props.doctype === 'CRM Deal') {
    if (data.value.ai_probability == null) return null
    return {
      probability: Math.round(data.value.ai_probability),
      confidence: data.value.ai_confidence,
      next_action: data.value.ai_next_action,
      recommendations: parseFactors(data.value.ai_recommendations),
      summary: data.value.ai_summary,
      lastUpdated: data.value.ai_last_analyzed,
    }
  }

  return null
})

const lastUpdated = computed(() => scoreData.value?.lastUpdated)

const scoreLabel = computed(() => {
  const score = scoreData.value?.score
  if (score >= 80) return 'Excellent'
  if (score >= 60) return 'Good'
  if (score >= 40) return 'Fair'
  if (score >= 20) return 'Low'
  return 'Cold'
})

const scoreColorClass = computed(() => {
  const score = scoreData.value?.score
  if (score >= 80) return 'bg-green-500'
  if (score >= 60) return 'bg-blue-500'
  if (score >= 40) return 'bg-yellow-500'
  if (score >= 20) return 'bg-orange-500'
  return 'bg-red-500'
})

const scoreTextClass = computed(() => {
  const score = scoreData.value?.score
  if (score >= 80) return 'text-green-600'
  if (score >= 60) return 'text-blue-600'
  if (score >= 40) return 'text-yellow-600'
  if (score >= 20) return 'text-orange-600'
  return 'text-red-600'
})

const probabilityColorClass = computed(() => {
  const prob = scoreData.value?.probability
  if (prob >= 75) return 'bg-green-500'
  if (prob >= 50) return 'bg-blue-500'
  if (prob >= 25) return 'bg-yellow-500'
  return 'bg-red-500'
})

const confidenceBarClass = computed(() => {
  const conf = scoreData.value?.confidence
  if (conf >= 0.8) return 'bg-green-500'
  if (conf >= 0.6) return 'bg-blue-500'
  if (conf >= 0.4) return 'bg-yellow-500'
  return 'bg-red-500'
})

function parseFactors(value) {
  if (!value) return []
  if (Array.isArray(value)) return value
  try {
    return typeof value === 'string' ? JSON.parse(value) : value
  } catch {
    return []
  }
}

async function refreshAnalysis() {
  if (!data.value?.name) return

  isLoading.value = true
  emit('refresh')

  try {
    const endpoint = props.doctype === 'CRM Lead' ? 'score_lead' : 'analyze_deal'
    const res = await frappe.call('crm.api.ai.' + endpoint, {
      [props.doctype === 'CRM Lead' ? 'lead_name' : 'deal_name']: data.value.name,
    })

    if (res.message && !res.message.error) {
      // Refresh the document data
      emit('updateField')
    }
  } catch (error) {
    console.error('AI analysis failed:', error)
  } finally {
    isLoading.value = false
  }
}
</script>
