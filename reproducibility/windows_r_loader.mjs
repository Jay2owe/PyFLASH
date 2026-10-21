// WebR 0.6 imports a Windows drive path from its worker. Resolve it as a file
// URL using Node's public loader hook, without modifying the R distribution.
import { registerHooks } from 'node:module';
import { pathToFileURL } from 'node:url';
registerHooks({resolve(specifier, context, nextResolve) {
    return nextResolve(/^[A-Za-z]:[\\/]/.test(specifier)
        ? pathToFileURL(specifier).href : specifier, context);
}});
