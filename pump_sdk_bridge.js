// pump_sdk_bridge.js
const { PumpSDK } = require("@pump-fun/pump-sdk");
const {
  Connection,
  Keypair,
  PublicKey,
} = require("@solana/web3.js");

const RPC_URL = "https://api.mainnet-beta.solana.com";

async function buyToken(
  mint,
  solAmount,
  slippage,
  secretKeyBase64,
) {
  const connection = new Connection(RPC_URL);
  const secretKey = Buffer.from(secretKeyBase64, "base64");
  const wallet = Keypair.fromSecretKey(secretKey);
  const sdk = new PumpSDK(connection, wallet);

  const tx = await sdk.buyToken(
    new PublicKey(mint),
    solAmount,
    slippage,
  );
  return tx.serialize().toString("base64");
}

async function sellToken(
  mint,
  multiplier,
  secretKeyBase64,
) {
  const connection = new Connection(RPC_URL);
  const secretKey = Buffer.from(secretKeyBase64, "base64");
  const wallet = Keypair.fromSecretKey(secretKey);
  const sdk = new PumpSDK(connection, wallet);

  const tx = await sdk.sellToken(
    new PublicKey(mint),
    multiplier,
  );
  return tx.serialize().toString("base64");
}

async function getRecentTokens() {
  const connection = new Connection(RPC_URL);
  const sdk = new PumpSDK(connection, null);
  const tokens = await sdk.getRecentTokens();
  return tokens;
}

const [
  ,
  ,
  action,
  mint,
  amount,
  slippageOrMultiplier,
  secretKeyBase64,
] = process.argv;

(async () => {
  try {
    let result;
    if (action === "buy") {
      result = await buyToken(
        mint,
        parseFloat(amount),
        parseFloat(slippageOrMultiplier),
        secretKeyBase64,
      );
      console.log(
        JSON.stringify({ serialized_tx: result }),
      );
    } else if (action === "sell") {
      result = await sellToken(
        mint,
        parseFloat(slippageOrMultiplier),
        secretKeyBase64,
      );
      console.log(
        JSON.stringify({ serialized_tx: result }),
      );
    } else if (action === "recent") {
      const tokens = await getRecentTokens();
      console.log(JSON.stringify({ tokens }));
    } else {
      throw new Error("Unknown action");
    }
  } catch (e) {
    console.error(e);
    process.exit(1);
  }
})();
