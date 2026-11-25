/// Maintainable word lists for the on-device recognizer (card #909).
///
/// Apple Vision's classifier (`VNClassifyImageRequest`) answers with a
/// taxonomy: broad parents (`structure`, `food`, `tableware`) next to the
/// concrete things (`apple`, `spoon`). A learner wants the objects, so the
/// parents are dropped before labels are matched to the dictionary. Edit the
/// lists here; nothing else in the code names a category.
library;

/// Labels that name a class of things or a scene, not something you can point
/// at. Dropped entirely (lower case, spaces instead of `_`).
const visionCategoryLabels = <String>{
  // materials / surfaces / generic structure
  'structure', 'wood processed', 'wood natural', 'material', 'textile',
  'fabric', 'metal', 'plastic', 'paper product', 'liquid', 'plant matter',
  'natural', 'pattern', 'texture', 'surface', 'object', 'item', 'thing',
  // vague adjectives that show nothing in the photo (問題回報 #1770; tagger's _VAGUE_ENGLISH_LABELS)
  'working', 'general', 'common', 'normal', 'basic', 'simple', 'main',
  'real', 'whole', 'different', 'various', 'other', 'good', 'nice', 'new', 'old',
  // food and kitchen parents
  'food', 'food and drink', 'drink', 'beverage', 'produce', 'fruit',
  'vegetable', 'baked goods', 'dessert', 'meal', 'dish', 'cuisine',
  'tableware', 'utensil', 'cutlery', 'kitchenware', 'cookware',
  'kitchen appliance', 'appliance', 'dinnerware', 'drinkware',
  // other parents
  'animal', 'mammal', 'bird', 'insect', 'reptile', 'pet',
  'vehicle', 'transportation', 'machine', 'device', 'electronics',
  'clothing', 'apparel', 'footwear', 'accessory', 'furniture', 'decor',
  'tool', 'equipment', 'instrument', 'toy', 'sports equipment',
  'building', 'architecture', 'room', 'indoor', 'outdoor', 'scene',
  'landscape', 'nature', 'sky', 'weather', 'water body', 'vegetation',
  'people', 'person', 'adult', 'child', 'crowd', 'body part',
  'text', 'sign', 'document', 'art', 'graphic', 'cartoon', 'illustration',
  'container', 'packaging', 'household', 'lighting', 'plumbing fixture',
};

/// Words Vision appends to a noun to say which sense it means (`cake regular`,
/// `road other`, `pot cooking`, `tea drink`). A label containing one is a
/// taxonomy tag, not a word (card #1212).
const visionQualifierWords = <String>{
  'regular', 'other', 'cooking', 'drink', 'room', 'raw', 'printed',
  'consumer', 'vehicle', 'natural', 'processed', 'indoor', 'outdoor',
};

/// Real words that Vision often gives with high confidence but that say
/// little about the photo. Kept, but ranked after the specific nouns.
const visionWeakLabels = <String>{
  'table',
  'floor',
  'wall',
  'ceiling',
  'window',
  'door',
  'shelf',
  'grass',
  'tree',
  'plant',
  'flower',
  'cloud',
  'water',
  'wood',
  'glass',
  'cup',
};

/// Multiplier applied to the score of a weak label.
const visionWeakFactor = 0.5;
