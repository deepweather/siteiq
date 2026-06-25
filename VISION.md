# SiteIQ — The operating system of the construction site

## The problem

Construction workers are productive 35% of their time. The other 65% is walking, waiting, and looking for things.

A $15.6 trillion global industry where nobody has real-time spatial intelligence about their own site. The superintendent walks the site, talks to foremen, uses gut feel. Materials get dumped wherever there's space. Toilets stay where they were placed on day one even though the work has moved 200 meters away. A crane worth €400/hour sits idle because nobody coordinated the schedule with the layout.

On a typical mid-size site, this waste adds up to roughly €81,000 per month — split between unproductive worker movement (~€23K), equipment sitting idle (~€46K), and materials staged far from where they're needed (~€12K).

The construction technology companies that exist today — Buildots, OpenSpace, Doxel — track progress against plan. They tell you *what happened*. None of them tell you *what to do about it*. A friend who leads construction at Black & Veatch, a major global EPC firm, has never heard of any of them. The market hasn't even started.

## The insight

Construction is repetitive but unmeasured. Every residential tower follows the same sequence: excavation → foundation → structure → MEP → close-in → finishes. Every hospital, every data center, every commercial fit-out. The process is standardized — the variance is in execution, not design.

But nobody has ever systematically observed and measured how construction actually works in practice. There is no dataset of "what good looks like" across thousands of sites. The knowledge lives in the heads of experienced superintendents and dies when they retire.

## The product

Cameras in. Decisions out.

Fixed cameras on the site, running off-the-shelf CV models, classifying every object: workers by trade, equipment by type and status, materials by category and location, temporary facilities. Project detections onto a 2D site plan. No 3D reconstruction needed, no BIM required. Just: camera sees object, object gets a class and a coordinate, coordinate gets painted on a canvas.

The product has four layers:

**Perception** — Fixed cameras + CV classification. Workers, equipment, materials, facilities. Position, state, type. This is straightforward with today's open-source models. These are large, high-contrast, distinctive objects. Not self-driving-car hard.

**World model** — Real-time 2D site map. Movement trails, density heatmaps, temporal accumulation. Where everything is and how it's changing. No fancy 3D reconstruction — just calibrate the cameras, create an initial floor measurement, track the pixels and paint them on a canvas.

**Process knowledge** — Templated construction sequences by building type. What phase each zone is in. What's coming in 2 weeks. The system knows: "this zone has structural steel going up, which means in 2-3 weeks it needs MEP rough-in, which means conduit and pipe need to be staged nearby now."

**Prescriptive optimization** — Move the toilet. Restage the rebar. Release the pump. Quantified in euros. This is where the value lives.

The first three layers are means to an end. The product is the fourth: specific, actionable, euro-denominated recommendations that make the site run at 60% productivity instead of 35%.

## The wedge

Show up. Show waste. Get paid.

Deploy your own camera towers — self-contained, solar/battery, 4G, positioned exactly where the CV needs them. A self-contained tower unit costs under €5K and can be built and deployed in hours. The site manager signs one piece of paper. His effort is zero.

First 30 days free. After 30 days, deliver a report: "This site lost €47,000 last month on three things we can see from cameras. Here's where the money went. Want us to fix it?"

That's not a sales pitch. That's a photograph of money on the floor.

Security monitoring — what BauWatch charges €1,000+/month for — comes free as a byproduct. If you're already classifying everything on site, "flag anything the model hasn't seen before" is a threshold on your existing pipeline. Safety/PPE compliance comes free. Progress tracking comes free. These are feature toggles, not products. Every separate vendor the customer is paying for today gets collapsed into a line item you give away.

**Unit economics**: ~€2,000/month revenue per site, ~€900/month cost (cameras, connectivity, compute), ~55% gross margin. Over an 18-month project lifecycle, that's €36K revenue and ~€20K gross profit per site.

**Go-to-market**: Land one site per general contractor. Prove results. The internal champion takes it to their ops director. The ops director mandates it across the portfolio. STRABAG runs hundreds of sites in Germany. You don't sell 500 sites individually — you sell 10 sites brilliantly.

## The Celonis parallel

Celonis's first hundred million in "process mining" revenue was finding invoices paid twice. Not sophisticated. Not AI. Just pointing at obvious money that nobody could see because nobody had the data.

The construction equivalent: "Your workers in zone C are walking 8 minutes to the nearest toilet, 5 times a day. That's €1,000 per day. Move the toilet." You don't need meter accuracy. You don't need a world model. You need a camera, a classifier, and arithmetic.

Start with the top 3 processes — toilet placement, equipment idle time, material staging distance. These are "duplicate invoice" level insights: obvious waste that everyone knows exists but nobody quantifies because nobody has the data.

After applying optimizations on a typical site: monthly waste drops from ~€81K to ~€27K. That's ~€54K/month recovered, or roughly €650K/year per site. The system pays for itself many times over.

## The moat: the data flywheel

The cameras are commodity. The CV models are commodity. What compounds is the process intelligence — empirical ground truth on how construction actually works, collected at a scale nobody has ever attempted.

**Object classification** improves with every site — more labeled examples of rebar stacks, scaffolding types, equipment states. Standard supervised learning flywheel.

**Process templates** get refined — the system learns that residential high-rises in Germany follow sequence X while commercial fit-outs in the US follow sequence Y, with statistical distributions on duration for each phase.

**Layout optimization** gets a training signal — correlating site layouts (where equipment and materials were staged) with actual throughput, idle time, and cost outcomes. After 500 sites, this is a dataset that has never existed in the history of construction.

**Predictive planning** improves — the system learns temporal patterns: when materials arrive relative to when they're needed, typical phase transition lags, seasonal effects on productivity.

## The endgame

**Phase 1 — Process intelligence.** Cameras → classification → waste detection → prescriptive optimization. The "duplicate invoice" wedge. Pays for itself from day one. Subsumes security (BauWatch), safety monitoring, and progress tracking as free byproducts.

**Phase 2 — Auto-generated world model.** Continuous camera feeds produce an auto-updated BIM without requiring one as input. This inverts the dependency: the system creates its own digital twin from observation. Opens the entire non-BIM market — renovations, developing world, small builders — which is the majority of global construction.

**Phase 3 — Construction intelligence platform.** Benchmarking data sold to developers, insurers, material suppliers. Predictive models for project financing and insurance underwriting. The dataset becomes a product.

**Phase 4 — Robotics OS.** The continuously-updated spatial-semantic world model becomes the platform that autonomous construction equipment plugs into. The cameras already provide perception. The process engine already knows what needs to happen where and when. Robots are commoditized actuators. The intelligence layer is the moat.

## The thesis in one sentence

Own the real-time world model of every construction site on earth, and everything else — optimization, safety, BIM, insurance, and eventually autonomous construction — is a layer on top of it.

## Market

~15,000 addressable sites active at any time in Germany alone (>€5M project value, >30 workers, >12 months duration). At €2,000/month per site, that's a €360M/year TAM in Germany. DACH extends to ~€800M. Western Europe to ~€2B. Global construction spend is $15.6 trillion. AI penetration in construction today is below 1%. The market is not competitive — it is empty.
