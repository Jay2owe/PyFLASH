"""Rebuild the two saved mouse batch definitions through PyFLASH.create_batch.

Inputs: original FLASH-export experiment roots, containing original object,
ROI and behaviour tables. Outputs: batch1/CK1I summary CSVs, new pickle cache,
effective settings and receipt. See README.md for the original notebook basis.
No image segmentation, statistical comparison or figure drawing is performed.
"""
import argparse
from pathlib import Path
from common import run_output


def conditions(cohort):
    from PyFLASH import conditionList, zipConditions, zipConditionLists
    syn, happ, nlgf = zipConditions(['Syn-mCherry', 'Syn-hAPPWT-mCh', 'Syn-hAPPNLGF-mCh'],
                                  ['Syn', 'hAPP', 'NLGF'], ['#787a7c', '#4369b2', '#9f1c1f'], 'Genotype')
    if cohort == 'timecourse':
        genotype = conditionList([syn, happ, nlgf], ['1-2', '2-3', '1-3'])
        time = conditionList(list(zipConditions([' 2 Weeks', ' 4 Weeks', ' 8 Weeks'],
                            ['WeekTwo', 'WeekFour', 'WeekEight'], [None] * 3, 'Time')))
        s2, s4, s8, h2, h4, h8, n2, n4, n8 = zipConditionLists(genotype, time)
        # Preserve the saved notebook's ordering and comparison list exactly.
        return conditionList([s2, h2, n2, s4, h4, n4, s8, h8, n8],
                             ['1-2', '2-3', '1-3', '4-5', '5-6', '4-6',
                              '7-8', '8-9', '7-9', '1-7', '2-8', '3-9'])
    genotype = conditionList([happ, nlgf])
    drug, vehicle = zipConditions([' + PF-670462', ' + Vehicle'], ['Drug', 'Veh'], [None, 'grey'], 'Drug')
    crossed = zipConditionLists(genotype, conditionList([vehicle, drug]),
                               ['black', '#4369b2', '#613c02', '#9f1c1f'])
    return conditionList(list(crossed), ['1-2', '3-4'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timecourse', type=Path, help='Original 2, 4, and 8 Weeks export root')
    parser.add_argument('--ck1i', type=Path, help='Original CK1I export root')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--threshold', type=int, default=30, help='Saved PyFLASH processing threshold')
    parser.add_argument('--pixel-size-setting', type=float, default=3.51998900003)
    parser.add_argument('--fallback-section-thickness-um', type=float, default=13.0)
    args = parser.parse_args()
    if not args.timecourse and not args.ck1i:
        parser.error('Supply --timecourse, --ck1i or both.')
    for path in (args.timecourse, args.ck1i):
        if path and not path.is_dir():
            parser.error(f'Not an experiment folder: {path}')
    from PyFLASH import Config, create_batch
    Config.THRESHOLD = args.threshold
    Config.PIXEL_SIZE = args.pixel_size_setting
    Config.SECTION_THICKNESS_UM = args.fallback_section_thickness_um
    settings = vars(args).copy()
    settings['failed_injection_exclusion'] = 'NLGFVeh20 (CK1I only; saved notebook rule)'
    with run_output(args.out, inputs=[], parameters=settings) as receipt:
        out = args.out.resolve()
        cache = out / 'cache'
        cache.mkdir()
        receipt['summary_rows'] = {}
        for cohort, name, path in [('timecourse', 'batch1', args.timecourse), ('ck1i', 'CK1I', args.ck1i)]:
            if path is None:
                continue
            batch = create_batch(name, conditions(cohort), str(path.resolve()), threshold=args.threshold,
                                 pickle_path=str(cache), rerun=True, import_images=False, progress=True)
            frame = batch.summary.copy()
            if cohort == 'ck1i':
                frame = frame.loc[frame['AnimalName'].ne('NLGFVeh20')].copy()
            frame.to_csv(out / f'{name}_summary.csv', index=False)
            receipt['summary_rows'][name] = len(frame)
            # Fingerprint actual imported tables, rather than scanning image folders.
            from common import sha256
            receipt.setdefault('imported_table_sha256', {}).update({str(p): sha256(p)
                for experiment in batch.experiment_list
                for entry in getattr(experiment, '_provenance_sources', [])
                for p in [Path(entry['path'])] if p.is_file()})


if __name__ == '__main__':
    main()
