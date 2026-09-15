// Independent SciPy BSpline/integration oracle for the frozen W4 source.
// Selection SHA256: 3ef847bad8c0cc9990fd01b40a0bd9a8ba09374153a166c1f6b910dea82b6e91
// These are implementation/rate guards, not new hardware measurements.
#include "DSP/ClassicSaw.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <complex>
#include <cstdio>
#include <limits>
#include <set>

namespace
{
struct Fixture { double phase, referenceIncrement, expected; };
constexpr std::array<Fixture,42> fixtures {{
    { 0, 0.0099773242630385485, 0.69783765664883179 },
    { 1.0000000000000001e-09, 0.0099773242630385485, 0.69783763607820803 },
    { 0.0123, 0.0099773242630385485, -1.403862082389 },
    { 0.125, 0.0099773242630385485, -0.74831002183160011 },
    { 0.374, 0.0099773242630385485, -0.25031002183160006 },
    { 0.73099999999999998, 0.0099773242630385485, 0.46368997816839991 },
    { 0.99999999900000003, 0.0099773242630385485, 0.48401076863646264 },
    { 0, 0.039909297052154194, 0.70290759115403156 },
    { 1.0000000000000001e-09, 0.039909297052154194, 0.70290758751137616 },
    { 0.0123, 0.039909297052154194, 0.56916485409602846 },
    { 0.125, 0.039909297052154194, -0.83550825213704261 },
    { 0.374, 0.039909297052154194, -0.24524008732640029 },
    { 0.73099999999999998, 0.039909297052154194, 0.46875991267359968 },
    { 0.99999999900000003, 0.039909297052154194, 0.48908068133041294 },
    { 0, 0.125, 0.71732041632885146 },
    { 1.0000000000000001e-09, 0.125, 0.71732041652729639 },
    { 0.0123, 0.125, 0.71570343045166973 },
    { 0.125, 0.125, -0.88726967743544471 },
    { 0.374, 0.125, -0.27005651276757575 },
    { 0.73099999999999998, 0.125, 0.69572798139762915 },
    { 0.99999999900000003, 0.125, 0.50349350155606276 },
    { 0, 0.25, 0.73849315417727102 },
    { 1.0000000000000001e-09, 0.25, 0.73849315527649328 },
    { 0.0123, 0.25, 0.7506179460079887 },
    { 0.125, 0.25, 0.46907832884943756 },
    { 0.374, 0.25, -0.41269811481575558 },
    { 0.73099999999999998, 0.25, -0.49546968349181608 },
    { 0.99999999900000003, 0.25, 0.52466623824385028 },
    { 0, 0.45000000000000001, 1.4228448713223862 },
    { 1.0000000000000001e-09, 0.45000000000000001, 1.4228448732522021 },
    { 0.0123, 0.45000000000000001, 1.4450438701708896 },
    { 0.125, 0.45000000000000001, 1.488253382385907 },
    { 0.374, 0.45000000000000001, -0.35447062974751614 },
    { 0.73099999999999998, 0.45000000000000001, -0.96563936300360786 },
    { 0.99999999900000003, 0.45000000000000001, 1.2090179544428807 },
    { 0, 7.8367346938775508, 0.10501181944482263 },
    { 1.0000000000000001e-09, 7.8367346938775508, 0.10501181921120996 },
    { 0.0123, 7.8367346938775508, 0.10214884744498676 },
    { 0.125, 7.8367346938775508, 0.076783137108894908 },
    { 0.374, 7.8367346938775508, 0.026062418378408649 },
    { 0.73099999999999998, 7.8367346938775508, -0.045890438570130747 },
    { 0.99999999900000003, 7.8367346938775508, -0.10881509540733061 },
}};
constexpr std::array<double,7> expectedRatiosDb { -7.2195956449054997, -12.830375366566722, -18.419595990269343, -24.785982495678105, -36.905786956390486, -29.738380404873539, -20.776626929798695 };

int checks=0,failures=0;
void require (bool ok,const char* what)
{
    ++checks;
    if (!ok) { ++failures; std::fprintf(stderr,"FAIL: %s\n",what); }
}

double continuousMean (double inc)
{
    // Split at every periodic polynomial boundary, then integrate each cubic
    // segment with an independent four-point Gaussian quadrature. Do not
    // confuse this continuous-phase mean with a sampled-window DC value.
    std::set<double> edges { 0.0,1.0 };
    for (int wrap=-33;wrap<=34;++wrap)
        for (int half=0;half<=8;++half)
            for (int sign : {-1,1})
            {
                const double phase=wrap+sign*half*.5*inc;
                if (phase>0 && phase<1) edges.insert(phase);
            }
    constexpr std::array<double,4> x {
        -.8611363115940525752,-.3399810435848562648,
         .3399810435848562648, .8611363115940525752 };
    constexpr std::array<double,4> w {
        .3478548451374538574,.6521451548625461426,
        .6521451548625461426,.3478548451374538574 };
    double sum=0,lo=0;
    for (auto it=std::next(edges.begin());it!=edges.end();++it)
    {
        const double hi=*it;
        for (std::size_t j=0;j<x.size();++j)
            sum+=(hi-lo)*.5*w[j]*septum::classic_saw::sample((hi+lo)*.5+(hi-lo)*.5*x[j],inc);
        lo=hi;
    }
    return sum;
}
}

int main()
{
    using septum::classic_saw::sample;
    double scalarWorst=0,harmonicWorst=0,meanWorst=0;
    for (const auto& f:fixtures)
    {
        const double error=std::abs(sample(f.phase,f.referenceIncrement)-f.expected);
        scalarWorst=std::max(scalarWorst,error);
        require(error<2e-12,"frozen SciPy source fixture");
    }
    // Compare phase-domain H2..H8 against the independent frozen SciPy source.
    // This tests physical support duration. It intentionally does not assert
    // that discrete sampling at different rates produces identical aliases.
    constexpr double pi=3.14159265358979323846;
    for (const double rate:{44100.0,48000.0,96000.0})
    {
        const double nativeIncrement=1760.0/rate;
        const double referenceIncrement=nativeIncrement*(rate/44100.0);
        std::array<std::complex<double>,8> harmonic {};
        for(int i=0;i<4096;++i)
        {
            const double phase=(i+.321)/4096;
            const double y=sample(phase,referenceIncrement);
            for (int h=1;h<=8;++h)
                harmonic[h-1]+=y*std::polar(1.0,-2*pi*h*phase);
        }
        for(int h=2;h<=8;++h)
        {
            const double ratio=20*std::log10(std::abs(harmonic[h-1])/std::abs(harmonic[0]));
            const double error=std::abs(ratio-expectedRatiosDb[h-2]);
            harmonicWorst=std::max(harmonicWorst,error);
            require(error<1e-9,"physical-duration harmonic shape at44.1/48/96k");
        }
    }
    int maxCopies=0;
    for(const double rate:{8000.0,11025.0,44100.0,48000.0,96000.0,192000.0,384000.0,768000.0})
        for(const double nativeIncrement:{1e-8,.001,.125,.45})
        {
            const double inc=nativeIncrement*(rate/44100.0);
            for(int i=0;i<129;++i)
            {
                const double phase=i/129.0;
                const auto value=sample(phase,inc);
                require(std::isfinite(value)&&std::abs(value)<10,"legalrate/increment finite bounded source");
                const int copies=static_cast<int>(std::floor(phase+4*inc)-std::ceil(phase-4*inc)+1);
                maxCopies=std::max(maxCopies,copies);
                require(copies<=63,"legalperiodic support bounded by63 copies");
            }
            const double mean=std::abs(continuousMean(inc));
            meanWorst=std::max(meanWorst,mean);
            require(mean<2e-12,"continuous-phase zero mean includingoverlap");
        }
    require(maxCopies==63,"maximumlegalperiodic overlap exercised");
    for(double phase:{0.,.37,.999999})
    {
        require(sample(phase,1e100)==sample(phase,septum::classic_saw::maxReferenceIncrement),"oversizeincrement clamps before integer bounds");
        require(sample(phase,0)==2*phase-1,"zero increment fallback");
        require(sample(phase,std::numeric_limits<double>::infinity())==2*phase-1,"nonfiniteincrement fallback");
    }
    require(sample(std::numeric_limits<double>::quiet_NaN(),.1)==0,"nonfinitephase fallback");
    require(sample(-.1,.1)==0&&sample(1.,.1)==0,"outofrangephase fallback");
    // A measured elapsed time is diagnostic, never a machine-dependent pass
    // threshold. Phase varies each call to prevent constant folding.
    const auto start=std::chrono::steady_clock::now();
    double sum=0;
    for(int i=0;i<100000;++i) sum+=sample((i%4096)/4096.0,.45);
    const double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    require(std::isfinite(sum),"CPUprobe finite");
    std::printf("ClassicSaw: %d checks, %d failures; scalar %.3g, harmonic %.3g dB, mean %.3g; maxcopies%d; 100k highpitch calls %.6fs\n",checks,failures,scalarWorst,harmonicWorst,meanWorst,maxCopies,seconds);
    return failures==0?0:1;
}
