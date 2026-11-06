/**
 * Bengali labels for the 44 IndicatorTarget rows.
 *
 * Keyed by "{partner}:{activity_code}". When the i18n language is 'bn',
 * IndicatorCard + TargetConfig + ExecutiveBento consult this map and
 * fall back to the English label served from the DB when no Bengali
 * variant exists.
 *
 * Translation policy
 * ──────────────────
 * - Direct translation where the term has a settled Bengali equivalent
 *   (e.g. "Outreach sessions" → "আউটরিচ সেশন").
 * - Phonetic Bengali for acronyms and clinical jargon that the
 *   workshop audience reads in Latin anyway (FSW → এফএসডব্লিউ,
 *   MPDSR → এমপিডিএসআর, ART → এআরটি, HIV → এইচআইভি, STI → এসটিআই,
 *   KP → কেপি, MHPSS → এমএইচপিএসএস).
 * - Mixed where useful for readability — e.g. "এইচআইভি/এসটিআই স্ক্রিনিং"
 *   keeps the slash + tech terms but Bengalises the surrounding text.
 *
 * Supervisor / RCH team can revise any string by editing this file.
 * No backend changes needed — these are presentation-only overrides.
 */

export const INDICATOR_LABELS_BN: Record<string, {
  activity?: string
  indicator?: string
}> = {
  // ─── PHD overall (obj=0) ────────────────────────────────────────────────
  'PHD:OVERALL': {
    activity:  'কভার করা ব্রোথেল (সামগ্রিক সূচক)',
    indicator: 'পিএইচডি সেবায় কভার করা ব্রোথেলের সংখ্যা',
  },

  // ─── PHD Objective 1 ────────────────────────────────────────────────────
  'PHD:1.1': {
    activity:  'এফএসডব্লিউদের জন্য এইচআইভি/এসটিআই স্ক্রিনিং ও পরিবার পরিকল্পনা পরামর্শ',
    indicator: 'এইচআইভি/এসটিআই স্ক্রিনিং ও পরিবার পরিকল্পনা পরামর্শ গ্রহণকারী এফএসডব্লিউ',
  },
  'PHD:1.2': {
    activity:  'জিবিভি ভুক্তভোগীদের স্ক্রিনিং ও সহায়তা; রেফারেল ব্যবস্থা সক্রিয়করণ',
    indicator: 'সেবার জন্য চিহ্নিত ও রেফার করা জিবিভি ভুক্তভোগী',
  },
  'PHD:1.3': {
    activity:  'ব্যক্তিগত ও দলগত মানসিক স্বাস্থ্য পরামর্শ',
    indicator: 'মানসিক স্বাস্থ্য পরামর্শ সেশন গ্রহণকারী এফএসডব্লিউ',
  },
  'PHD:1.4': {
    activity:  'লক্ষ্যভিত্তিক আউটরিচ ও স্বাস্থ্য শিক্ষা',
    indicator: 'পরিচালিত আউটরিচ সেশন (এফএসডব্লিউ ও ক্লায়েন্টদের কাছে পৌঁছানো)',
  },
  'PHD:1.5a': {
    activity:  'অপরিহার্য এসআরএইচআর / জিবিভি সরবরাহের প্রাপ্যতা নিশ্চিতকরণ',
    indicator: 'কনডম — সেবা কেন্দ্রে নিরবিচ্ছিন্ন সরবরাহ',
  },
  'PHD:1.5b': {
    activity:  'অপরিহার্য এসআরএইচআর / জিবিভি সরবরাহের প্রাপ্যতা নিশ্চিতকরণ',
    indicator: 'সিফিলিস স্ক্রিনিং কিট — নিরবিচ্ছিন্ন সরবরাহ',
  },
  'PHD:1.5c': {
    activity:  'অপরিহার্য এসআরএইচআর / জিবিভি সরবরাহের প্রাপ্যতা নিশ্চিতকরণ',
    indicator: 'হেপাটাইটিস বি স্ক্রিনিং কিট — নিরবিচ্ছিন্ন সরবরাহ',
  },
  'PHD:1.5d': {
    activity:  'অপরিহার্য এসআরএইচআর / জিবিভি সরবরাহের প্রাপ্যতা নিশ্চিতকরণ',
    indicator: 'হেপাটাইটিস সি স্ক্রিনিং কিট — নিরবিচ্ছিন্ন সরবরাহ',
  },
  'PHD:1.5e': {
    activity:  'অপরিহার্য এসআরএইচআর / জিবিভি সরবরাহের প্রাপ্যতা নিশ্চিতকরণ',
    indicator: 'এইচআইভি স্ক্রিনিং কিট — নিরবিচ্ছিন্ন সরবরাহ',
  },
  'PHD:1.6': {
    activity:  'এআরটি, ডায়াগনস্টিক ও চিকিৎসার জন্য রেফারেল সহায়তা',
    indicator: 'রেফার করা ও চিকিৎসায় নথিভুক্ত এইচআইভি/এসটিআই পজিটিভ কেস',
  },
  'PHD:1.7': {
    activity:  'কমিউনিটি-বান্ধব কেন্দ্র প্রতিষ্ঠা ও শক্তিশালীকরণ',
    indicator: 'কার্যকর ব্রোথেল-ভিত্তিক এসআরএইচআর সেবা কেন্দ্র',
  },
  'PHD:1.8': {
    activity:  'মোবাইল আউটরিচ স্বাস্থ্য সেবা',
    indicator: 'পরিচালিত মোবাইল স্বাস্থ্য ক্যাম্প',
  },

  // ─── PHD Objective 2 ────────────────────────────────────────────────────
  'PHD:2.1a': {
    activity:  'স্বাস্থ্য ব্যবস্থাপক ও সুপারভাইজারদের জন্য অ্যাডভোকেসি ওরিয়েন্টেশন / কর্মশালা',
    indicator: 'অন্তর্ভুক্তিমূলক এসআরএইচআর ও জিবিভি প্রতিক্রিয়ায় ওরিয়েন্ট করা ডিজিএফপি ব্যবস্থাপক',
  },
  'PHD:2.1b': {
    activity:  'স্বাস্থ্য ব্যবস্থাপক ও সুপারভাইজারদের জন্য অ্যাডভোকেসি ওরিয়েন্টেশন / কর্মশালা',
    indicator: 'জেলা/উপজেলা পর্যায়ের জিওবি কর্মী ও সেবা প্রদানকারী ওরিয়েন্ট',
  },
  'PHD:2.2': {
    activity:  'মিডওয়াইফ ও সেবা প্রদানকারীদের জন্য প্রশিক্ষণ',
    indicator: 'প্রশিক্ষণপ্রাপ্ত মেডিকেল অ্যাসিস্ট্যান্ট / মিডওয়াইফ / কাউন্সেলর',
  },
  'PHD:2.3': {
    activity:  'পিয়ার এডুকেটর ও কমিউনিটি নেতাদের জন্য প্রশিক্ষণ',
    indicator: 'প্রশিক্ষণপ্রাপ্ত পিয়ার এডুকেটর ও কমিউনিটি নেতা',
  },
  'PHD:2.4': {
    activity:  'ত্রৈমাসিক সমন্বয় সভা',
    indicator: 'অনুষ্ঠিত সমন্বয় সভা',
  },

  // ─── PHD Objective 3 (IEC materials — modules pending) ──────────────────
  'PHD:3.1a': {
    activity:  'বিলবোর্ড ও যোগাযোগ উপকরণ স্থাপন',
    indicator: 'স্থাপিত মেসেজ বোর্ড',
  },
  'PHD:3.1b': {
    activity:  'বিলবোর্ড ও যোগাযোগ উপকরণ স্থাপন',
    indicator: 'স্থাপিত পোস্টার',
  },
  'PHD:3.1c': {
    activity:  'বিলবোর্ড ও যোগাযোগ উপকরণ স্থাপন',
    indicator: 'স্থাপিত সাইনবোর্ড',
  },
  'PHD:3.1d': {
    activity:  'বিলবোর্ড ও যোগাযোগ উপকরণ স্থাপন',
    indicator: 'স্থাপিত বিলবোর্ড',
  },

  // ─── Bandhu Objective 1 ─────────────────────────────────────────────────
  'Bandhu:1.1': {
    activity:  'কেপির জন্য এইচআইভি/এসটিআই স্ক্রিনিং ও পরিবার পরিকল্পনা পরামর্শ',
    indicator: 'এইচআইভি/এসটিআই স্ক্রিনিং, পরামর্শ ও পরিবার পরিকল্পনা গ্রহণকারী কেপি ব্যক্তি',
  },
  'Bandhu:1.2': {
    activity:  'জিবিভি ভুক্তভোগী স্ক্রিনিং; প্রাথমিক সহায়তা ও রেফারেল প্রদান',
    indicator: 'স্ক্রিন, সহায়তা ও রেফার করা জিবিভি ভুক্তভোগী',
  },
  'Bandhu:1.3': {
    activity:  'ব্যক্তিগত ও দলগত এমএইচপিএসএস পরামর্শ সেশন',
    indicator: 'প্রদানকৃত এমএইচপিএসএস পরামর্শ সেশন',
  },
  'Bandhu:1.4a': {
    activity:  'লক্ষ্যভিত্তিক আউটরিচ ও স্বাস্থ্য শিক্ষা সেশন',
    indicator: 'পরিচালিত আউটরিচ ও স্বাস্থ্য শিক্ষা সেশন',
  },
  'Bandhu:1.5a': {
    activity:  'সেবা কেন্দ্রে এসআরএইচআর / জিবিভি সরবরাহ নিশ্চিতকরণ',
    indicator: 'নিরবিচ্ছিন্ন অপরিহার্য পণ্য বজায় রাখা সেবা কেন্দ্র',
  },
  'Bandhu:1.5b': {
    activity:  'সেবা কেন্দ্রে এসআরএইচআর / জিবিভি সরবরাহ নিশ্চিতকরণ',
    indicator: 'এসটিআই ও এইচআইভি পরীক্ষা সেবা গ্রহণকারী কেপি',
  },
  'Bandhu:1.6': {
    activity:  'কেপি ক্লিনিক (ঢাকা) — লজিস্টিক/রক্ষণাবেক্ষণ সহায়তা',
    indicator: 'লজিস্টিক, সরবরাহ ও রক্ষণাবেক্ষণ সহায়তা পাওয়া কেপি ক্লিনিক',
  },
  'Bandhu:1.7': {
    activity:  'এআরটি নথিভুক্তকরণ, ডায়াগনস্টিক ও চিকিৎসার জন্য রেফারেল সহায়তা',
    indicator: 'এআরটি / ডায়াগনস্টিক / চিকিৎসায় রেফার ও সংযুক্ত কেপি ক্লায়েন্ট',
  },
  'Bandhu:1.8': {
    activity:  'কমিউনিটি-বান্ধব ড্রপ-ইন কেন্দ্র প্রতিষ্ঠা ও শক্তিশালীকরণ',
    indicator: 'প্রতিষ্ঠিত বা শক্তিশালী করা ড্রপ-ইন কেন্দ্র',
  },
  'Bandhu:1.9': {
    activity:  'কেপিদের জন্য মোবাইল আউটরিচ স্বাস্থ্য সেবা',
    indicator: 'মোবাইল ক্যাম্পের মাধ্যমে স্বাস্থ্য সেবা গ্রহণকারী কেপি ব্যক্তি',
  },

  // ─── Bandhu Objective 2 ─────────────────────────────────────────────────
  'Bandhu:2.1': {
    activity:  'স্বাস্থ্য খাতের ব্যবস্থাপক ও সুপারভাইজারদের জন্য কাঠামোবদ্ধ ওরিয়েন্টেশন',
    indicator: 'ওরিয়েন্ট করা সরকারি স্বাস্থ্য খাতের ব্যবস্থাপক ও সুপারভাইজার',
  },
  'Bandhu:2.2': {
    activity:  'মিডওয়াইফ ও সেবা প্রদানকারীদের জন্য প্রশিক্ষণ',
    indicator: 'প্রশিক্ষণপ্রাপ্ত মিডওয়াইফ ও সম্মুখসারির প্রদানকারী',
  },
  'Bandhu:2.3': {
    activity:  'ত্রৈমাসিক জিওবি-এনজিও সমন্বয় সভা',
    indicator: 'জিওবি কর্মী, মিডওয়াইফ ও এনজিওদের মধ্যে সমন্বয় সভা',
  },
  'Bandhu:2.4': {
    activity:  'ত্রৈমাসিক সিবিও ও নেটওয়ার্ক সমন্বয় সভা',
    indicator: 'সিবিও ও কমিউনিটি নেটওয়ার্কের মধ্যে সমন্বয় সভা',
  },
  'Bandhu:2.5': {
    activity:  'কমিউনিটি নেতা ও পিয়ার এডুকেটরদের জন্য প্রশিক্ষণ (এলজিবিটিকিউ)',
    indicator: 'প্রশিক্ষণপ্রাপ্ত কমিউনিটি নেতা ও পিয়ার এডুকেটর',
  },
  'Bandhu:2.6': {
    activity:  'বিশেষ দিবস পালনে সহায়তা (যেমন বিশ্ব এইডস দিবস, মানবাধিকার দিবস)',
    indicator: 'সহায়তা করা জাতীয় ও আন্তর্জাতিক দিবস',
  },

  // ─── Bandhu Objective 4 ─────────────────────────────────────────────────
  'Bandhu:4.1': {
    activity:  'অন্তর্ভুক্তিমূলক আইইসি / এসবিসিসি উপকরণ তৈরি ও প্রচার',
    indicator: 'তৈরি ও প্রচার করা আইইসি / এসবিসিসি উপকরণ ও মাল্টিমিডিয়া পণ্য',
  },
  'Bandhu:4.2': {
    activity:  'সর্বজনীন বার্তা প্রদর্শন স্থাপন (মুদ্রিত + ই-বিলবোর্ড)',
    indicator: 'স্থাপিত সর্বজনীন বার্তা প্রদর্শন (৪০ মুদ্রিত + ১৬ ই-বিলবোর্ড)',
  },

  // ─── CIPRB (all targets null until supervisor confirms) ─────────────────
  'CIPRB:F.C': {
    activity:  'ফিস্টুলা কর্নার — জেলা হাসপাতালের ডায়াগনোসিস রেকর্ড',
    indicator: 'জেলা হাসপাতাল ফিস্টুলা কর্নারে নির্ণীত ফিস্টুলা কেস',
  },
  'CIPRB:F.Camp': {
    activity:  'ফিস্টুলা ক্যাম্পেইন — বাড়ি-বাড়ি ক্যাম্পেইন রেকর্ড',
    indicator: 'বাড়ি পরিদর্শনের মাধ্যমে চিহ্নিত সন্দেহভাজন ফিস্টুলা কেস',
  },
  'CIPRB:B': {
    activity:  'বেসলাইন মূল্যায়ন — সিআইপিআরবি পরিচালিত সমীক্ষা ডেটা',
    indicator: 'বেসলাইন মূল্যায়ন রেকর্ড এন্ট্রি',
  },
}

// ─── Unit translations ─────────────────────────────────────────────────────

export const UNITS_BN: Record<string, string> = {
  individuals:  'ব্যক্তি',
  survivors:    'ভুক্তভোগী',
  sessions:     'সেশন',
  pcs:          'পিস',
  boxes:        'বাক্স',
  cases:        'কেস',
  centers:      'কেন্দ্র',
  camps:        'ক্যাম্প',
  managers:     'ব্যবস্থাপক',
  staff:        'কর্মী',
  participants: 'অংশগ্রহণকারী',
  meetings:     'সভা',
  events:       'ইভেন্ট',
  tests:        'পরীক্ষা',
  clinics:      'ক্লিনিক',
  materials:    'উপকরণ',
  installations: 'ইনস্টলেশন',
  brothels:     'ব্রোথেল',
  visits:       'পরিদর্শন',
  surveys:      'সমীক্ষা',
  count:        'গণনা',
}

// ─── Lookup helpers ────────────────────────────────────────────────────────

export function bnIndicatorLabel(
  partnerCode: string,
  activityCode: string,
  fallbackEn: string,
): string {
  const key = `${partnerCode}:${activityCode}`
  return INDICATOR_LABELS_BN[key]?.indicator ?? fallbackEn
}

export function bnActivityLabel(
  partnerCode: string,
  activityCode: string,
  fallbackEn: string,
): string {
  const key = `${partnerCode}:${activityCode}`
  return INDICATOR_LABELS_BN[key]?.activity ?? fallbackEn
}

export function bnUnit(unitEn: string): string {
  return UNITS_BN[unitEn] ?? unitEn
}
