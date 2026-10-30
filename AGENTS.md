# vue-bpmn-designer Collaboration Rules

## 1. Project Scope and Stack

This project is a local diagnostic workflow platform: a Vue BPMN designer, a Python HTTP backend and worker coordinator, and a Java Flowable runtime. It supports modeling, properties, linting, token simulation, Python project integration, human reviews, execution history, and English/Chinese localization.

- Vue 3.5, TypeScript, and Vite 6
- Pinia 3 and `pinia-plugin-persistedstate`
- Element Plus and SCSS
- `bpmn-js`, `diagram-js`, `bpmnlint`, and related plugins
- CodeMirror 6
- `vue-i18n` and VueUse
- Python 3.9+ and the official Flowable external-worker client
- Java 17+ and Flowable 7.1; Maven 3.8.8+ for building the runtime
- Use `pnpm` exclusively. Do not use `npm` or `yarn`.

There is no frontend routing layer or separate test framework. The backend API and automated `scripts/verify-*` regression scripts already exist; reuse them instead of scaffolding replacement infrastructure.

Parallel execution uses Flowable gateways and independent tokens. Serial execution uses the persistent queue in `DiagnosisScheduler`. Flowable persists waits, variables and history; Python sessions retain native objects in memory. Declared business checkpoints preserve native state, release idle interpreters at human waits, and restore compatible sessions after worker/backend restarts. Unsupported or uncertain state must fail closed; see docs/RECOVERY.md.

## 2. Commands

```bash
pnpm dev          # Prepare/reuse Java and Python services, then start the frontend
pnpm dev:frontend # Start only the frontend
pnpm type-check   # Run Vue and TypeScript checks
pnpm build-only   # Run the Vite production build
pnpm build        # Run type checking and the production build
pnpm verify       # Run all regression scripts with isolated verification engines
pnpm verify --group unit   # Run scripts that do not require Java
pnpm verify --group engine # Run real-engine regression scripts
pnpm lint         # Run ESLint with automatic fixes; modifies files
pnpm format       # Format all files under src; modifies files
```

- Run checks proportional to the change. For build, configuration, or cross-module changes, run both `pnpm type-check` and `pnpm build-only`.
- `lint` and `format` write to many files. If the worktree contains unrelated changes, run ESLint or Prettier only on files changed by the current task.
- There is no `test` script. `pnpm verify` discovers every `scripts/verify-*.py` and `scripts/verify-*.mjs`; classify new real-engine scripts in `scripts/verify.py`. The runner uses the prepared backend interpreter (or `PYTHON`/`--python`), random local ports and temporary databases. Logs are under `backend/.local/verification/`.
- Rebuild Java changes before engine verification: `mvn -B -ntp -f flowable-runtime/pom.xml -DskipTests package`. When dependencies are unavailable but an existing executable JAR is present, `python scripts/rebuild-flowable-local.py` compiles current sources against its bundled dependencies without downloading replacements.
- GitHub Actions runs frontend checks and all regression scripts on Windows, including the mocked Windows reference-file launcher checks. Report the commands actually run and any remaining failures.

## 3. Directory Responsibilities

- `src/views/ProcessDesigner/BpmnModeler.tsx`: creates the Modeler and registers `additionalModules`, the Flowable moddle descriptor, linting, and plugins.
- `src/views/ProcessDesigner/BpmnPanel.vue`: selects and renders properties-panel components for the current BPMN element.
- `src/views/ProcessDesigner/Panel/`: properties-panel UI for individual BPMN element types.
- `src/hooks/useService.ts`: stores the current element and didi injector, exposes bpmn-js services, and updates Moddle properties.
- `src/views/ProcessDesigner/utils/`: shared element, event-definition, extension-element, and validation helpers. Reuse these before adding new logic.
- `src/views/ProcessDesigner/Modeling/`, `Renderer/`, `Replace/`, `Palette/`, `ContextPad/`, and `PopupMenu/`: bpmn-js extension modules.
- `src/views/ProcessDesigner/Lint/`: static resolver, lint configuration, and custom lint rules.
- `src/views/ProcessDesigner/flowable.json`: Flowable moddle descriptor.
- `src/languages/`: UI and bpmn-js localization resources.
- `src/stores/`: Pinia Setup Stores and persisted-state plugin registration.
- `src/types/`: business types and supplemental third-party declarations.
- `src/rules/diagnosis-connections.json`: the single connection-rule table used by the frontend and Python compiler. `generic` preserves ordinary BPMN modeling boundaries; the runtime compiler still rejects unsupported executable constructs.
- `backend/server.py`: local HTTP API, historical execution projection and project registration.
- `backend/flowable_bridge.py`: diagnostic compilation and Flowable REST access.
- `backend/execution_manager.py`, `flowable_worker.py`, `python_sessions.py`, `python_runtime.py`: worker recovery, native sessions and display projections. `session_checkpoint.py` implements the explicit state codec and atomic checkpoint store; do not substitute display projections or replay old actions.
- `backend/execution_history.py` and `ExecutionHistoryController.java`: revision-based historical projections, cursor resets and bounded caches. The frontend merges updates/removals in `Execution/history.ts`.
- `src/stores/modules/execution.ts`: persisted monitor IDs only; do not persist business snapshots in browser storage.
- `scripts/runtime-manifest.mjs`: source/JAR identity for prebuilt artifacts; building Java sources must refresh the manifest.
- `flowable-runtime/src/main/java/local/diagnosis/`: persistent scheduling and transactional human reviews.
- `scripts/verify.py`, `scripts/verify-*`: unified verification runner and regression cases; old example migration checks must explicitly reject unsupported legacy branch definitions.
- `src/typings/auto-imports.d.ts` and `src/typings/components.d.ts`: generated files; never maintain them manually.

Use the `@/` alias for internal modules instead of adding deep relative imports.

## 4. Vue, State, and Component Rules

- Vue SFCs should use `<script setup lang="ts">` and the Composition API. Do not add Options API code unless an existing bpmn-js extension specifically requires a class or TSX implementation.
- Vue runtime APIs and Element Plus APIs/components are auto-imported. In new or modified code, do not manually import `ref`, `computed`, `ElMessage`, `ElButton`, and similar APIs. Use `import type` for types. Element Plus icons still require explicit imports.
- Props, Emits, Expose APIs, and form data require explicit types. Reuse `src/types` instead of duplicating interfaces across components.
- Pinia stores must use Setup Store syntax. Persist cross-session state with the existing `pinia-plugin-persistedstate` configuration and `pick`; do not access `localStorage` directly.
- Use `computed` for derived state. Do not use `watch` to copy state that can be calculated directly.
- Do not add a dependency for a small amount of code. Prefer existing helpers, browser APIs, and installed dependencies.

## 5. bpmn-js and Flowable Rules

### 5.1 Reading Models and Accessing Services

- Properties-panel components must use `useBpmnContextService()` to access `selectedElement`, `getService`, and `updateProperties`.
- Read business objects with `getBusinessObject`; use `is` and `isAny` for type checks instead of guessing from object shape.
- Register new bpmn-js modules in `BpmnModeler.tsx` under `additionalModules`. Classes managed by didi must declare the correct `$inject` list.

### 5.2 Model Updates and the Undo Stack

- Every change persisted to BPMN XML must pass through the bpmn-js command stack so undo/redo, events, and rendering remain correct.
- Use `modeling.updateProperties` for normal element properties. Use the existing `updateProperties` wrapper, `modeling.updateModdleProperties`, or the matching command-stack command for ModdleElement properties.
- Never mutate an existing business object, ModdleElement collection, or persistence-related DOM directly.
- Create elements with `bpmnFactory` and the existing `createElement` helper. Use `ExtensionElementsUtil.ts` to query, add, or remove extension elements.
- Replace collections with new arrays instead of calling `push` or `splice`. Only newly created ModdleElements may have `$parent` assigned through existing helpers.
- Direct SVG or DOM manipulation is allowed only in render-only modules such as Renderer. DOM state must never replace BPMN model state.

### 5.3 Flowable Semantics

- Use the `flowable:` prefix for Flowable extensions and `bpmn:` for standard BPMN elements. Do not introduce the `camunda:` prefix.
- When changing a Flowable extension structure, check `flowable.json`, `src/types`, XML serialization, and the properties panel together.
- Complex model operations require comments that explain why the command, parent relationship, or boundary handling is necessary. Do not write comments that merely restate the code.
- Keep an entire human review in one Flowable command context as well as one Spring transaction. Separate engine calls can reload a newer variable revision while writing an older snapshot, silently losing audit records. On optimistic conflicts, roll back and return HTTP 409; never retry equipment actions automatically.
- Read completed execution data through historical variables. Review endpoints use runtime variables only while an active task exists. Preserve legacy documentation metadata through `DiagnosticMetadata` when reading old deployments.
- Checkpoints require explicit module stateless declarations/global-state hooks and synchronous native-object hooks. Capture only after concurrent calls finish, persist before acknowledging the job, and cache responses until acknowledgment. Never recover an in-flight/unsupported snapshot or silently accept changed source, dependencies or session identity.
- Verify changes to monitoring with mutable activity completion, variable deletion, cursor expiry/backend restart, definition mismatch and stop-monitor behavior. Both launcher health checks and frontend protocol checks must reject obsolete execution APIs.

## 6. Localization Rules

The UI supports `en-US` and `zh-CN`. Browser language selects the initial locale, and Pinia persists the user's choice. Every user-visible message must support both languages.

- Use `$t('ui.xxx')` for shared, stable semantic messages and update both `langs/en-US/index.ts` and `langs/zh-CN/index.ts`.
- In properties-panel templates, wrap Chinese source text with `$tu('中文')`. In scripts, use `translateUi('中文')` and add the English mapping to `langs/en-US/uiText.ts`.
- For dynamic sentences, use `$tu(chineseText, englishText)` or `translateUi(chineseText, englishText)` instead of relying on a dynamic dictionary key that cannot match.
- Use `translateUiHtml` for static HTML help such as CodeMirror descriptions. Do not insert unlocalized visible Chinese text directly.
- bpmn-js menus, Palette entries, and lint messages use English source text as keys. Add Chinese translations under `bpmn` in `zh-CN/index.ts`.
- Validation rules must react to locale changes. Define static rule objects with `computed`; call `translateUi` inside custom validators at validation time.
- Code comments and internal developer notes use Simplified Chinese. Keep the default `README.md` in English and the Chinese version in `README.zh-CN.md`; keep feature descriptions synchronized.

## 7. TypeScript, Naming, and Comments

- Variables, functions, classes, types, and other code identifiers must use English. Do not use pinyin identifiers.
- Prefer precise unions, generics, and public third-party types. Local `any` is acceptable only at an external boundary that cannot be typed accurately; do not let it spread into business logic.
- Put supplemental third-party declarations in `src/types/*.d.ts`. Do not modify dependencies or generated declaration files.
- Comments must explain business reasons, protocol constraints, or boundary conditions. Remove comments that only narrate code behavior.
- Logs and developer-facing errors may use English. User-visible errors must use localization.

## 8. Formatting, Scope, and Verification

- Follow Prettier: no semicolons, single quotes, and a 100-character line width. Follow the existing ESLint flat configuration.
- Preserve existing user changes. Do not perform unrelated formatting, refactoring, dependency upgrades, or file moves.
- Fix shared root causes instead of patching individual callers. Prefer removing duplicate logic, and do not add abstractions for hypothetical future needs.
- When modifying a properties panel, verify Chinese, English, live locale switching, model persistence, undo, redo, and XML prefixes.
- When modifying a bpmn-js extension, verify module registration, didi injection names, command-stack integration, event dispatch, and rerendering.
- At handoff, report the commands actually run. If a check fails, distinguish errors introduced by the current change from existing repository failures.

## 9. 沟通风格

- 和用户交流时，像两个同事在对话：自然、直接、简洁，先说重点，需要时再解释。不要像写论文一样堆砌术语、铺陈背景或过度分节；技术细节要讲清楚，但用日常、易懂的表达。
-
用户说一句短话，先考虑一句自然接话够不够，允许留白，不用把所有问题一次说完。
-

