// Trusted parser only: never imports or executes the reviewed project/configuration.
const ts = require("../frontend/node_modules/typescript");
const fs = require("fs");
const rawInputs = JSON.parse(fs.readFileSync(0, "utf8"));
const inputs = rawInputs.filter((f) => /\.[jt]sx?$/.test(f.path));
const pathUtil = require("node:path");
const virtual = new Map(
  rawInputs.map((f) => ["/repo/" + f.path.replaceAll("\\", "/"), f.content]),
);
const libRoot = pathUtil.dirname(ts.getDefaultLibFilePath({}));
const trustedLib = (p) =>
  pathUtil.resolve(p).startsWith(libRoot + pathUtil.sep) &&
  /^lib\..*\.d\.ts$/.test(pathUtil.basename(p));
const options = {
  target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.CommonJS,
  moduleResolution: ts.ModuleResolutionKind.Node10,
  allowJs: true,
  checkJs: false,
  strict: true,
  noEmit: true,
  skipLibCheck: true,
  jsx: ts.JsxEmit.Preserve,
};
const configSource = virtual.get("/repo/tsconfig.json");
if (configSource) {
  const config = ts.parseConfigFileTextToJson("tsconfig.json", configSource);
  if (!config.error) {
    const supplied = config.config?.compilerOptions || {};
    for (const key of [
      "strict",
      "strictNullChecks",
      "strictFunctionTypes",
      "noImplicitAny",
      "noUncheckedIndexedAccess",
      "exactOptionalPropertyTypes",
    ]) {
      if (typeof supplied[key] === "boolean") options[key] = supplied[key];
    }
    if (supplied.paths && typeof supplied.paths === "object") {
      options.paths = supplied.paths;
      options.baseUrl = "/repo";
    }
    if (
      typeof supplied.baseUrl === "string" &&
      !pathUtil.posix.resolve("/repo", supplied.baseUrl).startsWith("/repo/../")
    )
      options.baseUrl = pathUtil.posix.resolve("/repo", supplied.baseUrl);
  }
}
const host = ts.createCompilerHost(options);
const read = (p) =>
  virtual.get(p) ?? (trustedLib(p) ? fs.readFileSync(p, "utf8") : undefined);
host.readFile = read;
host.fileExists = (p) => virtual.has(p) || (trustedLib(p) && fs.existsSync(p));
host.getSourceFile = (p, language) => {
  const text = read(p);
  return text === undefined
    ? undefined
    : ts.createSourceFile(p, text, language, true);
};
host.getCurrentDirectory = () => "/repo";
host.directoryExists = (p) =>
  p === "/repo" ||
  [...virtual.keys()].some((f) => f.startsWith(p + "/")) ||
  p === libRoot;
host.getDirectories = () => [];
host.realpath = (p) => p;
host.writeFile = () => {};
const program = ts.createProgram(
  inputs.map((f) => "/repo/" + f.path),
  options,
  host,
);
const checker = program.getTypeChecker();
const semanticCodes = new Set([
  2322, 2345, 2554, 2555, 2769, 2355, 2366, 18047, 18048, 2531, 2532,
]);
const out = inputs.map(({ path, content }) => {
  const kind = path.endsWith(".tsx")
    ? ts.ScriptKind.TSX
    : path.endsWith(".jsx")
      ? ts.ScriptKind.JSX
      : /\.ts$/.test(path)
        ? ts.ScriptKind.TS
        : ts.ScriptKind.JS;
  const sf = ts.createSourceFile(
    path,
    content,
    ts.ScriptTarget.Latest,
    true,
    kind,
  );
  const findings = sf.parseDiagnostics.map((d) => ({
    rule: "js:syntax",
    category: "bug",
    line: sf.getLineAndCharacterOfPosition(d.start || 0).line + 1,
    message: ts.flattenDiagnosticMessageText(d.messageText, " "),
  }));
  const symbols = [],
    imports = [],
    bindings = [],
    calls = [],
    resolved_references = [];
  const projectFile = program.getSourceFile("/repo/" + path);
  if (projectFile) {
    for (const diagnostic of program.getSemanticDiagnostics(projectFile)) {
      if (
        semanticCodes.has(diagnostic.code) &&
        !path.endsWith(".js") &&
        !path.endsWith(".jsx")
      )
        findings.push({
          rule: "js:type-" + diagnostic.code,
          category: "bug",
          line:
            projectFile.getLineAndCharacterOfPosition(diagnostic.start || 0)
              .line + 1,
          message: ts.flattenDiagnosticMessageText(diagnostic.messageText, " "),
        });
    }
    function references(node) {
      if (ts.isCallExpression(node)) {
        const expr = ts.isPropertyAccessExpression(node.expression)
          ? node.expression.name
          : node.expression;
        let symbol = checker.getSymbolAtLocation(expr);
        if (symbol?.flags & ts.SymbolFlags.Alias)
          symbol = checker.getAliasedSymbol(symbol);
        for (const decl of symbol?.getDeclarations() || []) {
          const target = decl.getSourceFile();
          if (target.fileName.startsWith("/repo/"))
            resolved_references.push({
              name: decl.name?.getText(target) || symbol.name,
              export_name: symbol.name,
              local_name: expr.getText(projectFile),
              path,
              line:
                projectFile.getLineAndCharacterOfPosition(node.getStart())
                  .line + 1,
              target_path: target.fileName.slice(6),
              target_line:
                target.getLineAndCharacterOfPosition(decl.getStart()).line + 1,
              relationship: "compiler_resolved_call",
            });
        }
      }
      ts.forEachChild(node, references);
    }
    references(projectFile);
  }
  function walk(n) {
    if (ts.isImportDeclaration(n) && ts.isStringLiteral(n.moduleSpecifier)) {
      imports.push(n.moduleSpecifier.text);
      const named = n.importClause?.namedBindings;
      if (named && ts.isNamedImports(named))
        for (const e of named.elements)
          bindings.push({
            module: n.moduleSpecifier.text,
            name: e.propertyName?.text || e.name.text,
            local: e.name.text,
          });
    }
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression))
      calls.push({
        name: n.expression.text,
        line: sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1,
        arguments: n.arguments.length,
        spread: n.arguments.some(ts.isSpreadElement),
      });
    if (
      (ts.isFunctionDeclaration(n) ||
        ts.isMethodDeclaration(n) ||
        ts.isArrowFunction(n)) &&
      n.body
    ) {
      const name =
        n.name?.getText(sf) ||
        (n.parent && ts.isVariableDeclaration(n.parent)
          ? n.parent.name.getText(sf)
          : null);
      if (name)
        symbols.push({
          name,
          line: sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1,
          end: sf.getLineAndCharacterOfPosition(n.end).line + 1,
          parameters: n.parameters.map((p) => ({
            name: p.name.getText(sf),
            required: !p.questionToken && !p.initializer && !p.dotDotDotToken,
          })),
          exported: !!n.modifiers?.some(
            (m) => m.kind === ts.SyntaxKind.ExportKeyword,
          ),
        });
    }
    if (
      ts.isCallExpression(n) &&
      ts.isPropertyAccessExpression(n.expression) &&
      n.expression.name.text === "forEach" &&
      n.arguments.some(
        (a) =>
          (ts.isArrowFunction(a) || ts.isFunctionExpression(a)) &&
          a.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword),
      )
    )
      findings.push({
        rule: "js:async-foreach",
        category: "bug",
        line: sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1,
        message:
          "forEach discards promises returned by async callbacks. Await Promise.all with map, or use an awaited for…of loop when completion order matters.",
      });
    if (
      ts.isBinaryExpression(n) &&
      [
        ts.SyntaxKind.EqualsEqualsToken,
        ts.SyntaxKind.ExclamationEqualsToken,
      ].includes(n.operatorToken.kind) &&
      n.left.kind !== ts.SyntaxKind.NullKeyword &&
      n.right.kind !== ts.SyntaxKind.NullKeyword
    )
      findings.push({
        rule: "js:loose-equality",
        category: "style",
        line: sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1,
        message:
          "Loose equality performs implicit coercion. Prefer strict equality unless coercion is intentional.",
      });
    ts.forEachChild(n, walk);
  }
  walk(sf);
  return {
    path,
    symbols,
    imports,
    bindings,
    calls,
    resolved_references,
    findings,
  };
});
process.stdout.write(JSON.stringify(out));
